"""Tool Runtime — ACP.TOOL.REQUEST tüketir; dry-run, schema validation, rate-limit,
compensation kaydı ile action governance katmanı (v0.9.1)."""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

import nats
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from agentic_schemas.acp.v1 import ErrorCode, ErrorMessage, ResultMessage, ResultPayload, TaskMessage
from agentic_schemas.events.v1 import Subject

from . import compensator, rate_limiter, schema_validator
from .db import SessionLocal, ToolInvocation, ToolCompensation
from .tools import HANDLERS, load_catalog

NATS_URL = os.environ.get("NATS_URL", "nats://nats:4222")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
DURABLE = "tool-runtime"
NON_RETRYABLE = {"PERMISSION", "SCHEMA"}


def _now():
    return datetime.now(timezone.utc)


async def run() -> None:
    nc = await nats.connect(NATS_URL, name="tool-runtime", reconnect_time_wait=2, max_reconnect_attempts=-1)
    js = nc.jetstream()
    catalog = load_catalog()
    allow = set(catalog.get("permissions", {}).get("allow", []))
    redis = await redis_from_url(REDIS_URL, decode_responses=True)

    async def _publish_ok(task: TaskMessage, result: dict, exec_id: str, dry_run: bool = False) -> None:
        payload = {**result, "exec_id": exec_id}
        if dry_run:
            payload["dry_run"] = True
        msg = ResultMessage(from_agent="tool-runtime", to_agent="kaptan", trace_id=task.trace_id,
                            in_reply_to=task.message_id, skill=task.skill, timestamp=int(time.time()),
                            payload=ResultPayload(result=payload, confidence=1.0))
        await js.publish(Subject.TOOL_RESULT.value, msg.model_dump_json(by_alias=True).encode())

    async def _publish_fail(task: TaskMessage, code: str, message: str, retry_after: int = 0) -> None:
        err = ErrorMessage(from_agent="tool-runtime", to_agent="kaptan", trace_id=task.trace_id,
                           in_reply_to=task.message_id, timestamp=int(time.time()),
                           error_code=ErrorCode(code) if code in ErrorCode.__members__ else ErrorCode.UNKNOWN,
                           message=message)
        if retry_after:
            err.payload["retry_after"] = retry_after
        await js.publish(Subject.TOOL_RESULT.value, err.model_dump_json(by_alias=True).encode())

    async def handle(msg) -> None:
        try:
            task = TaskMessage.model_validate(json.loads(msg.data))
            inputs = task.payload.inputs or {}
            tool = task.payload.tool
            args = task.payload.tool_args or {}
            exec_id = inputs.get("exec_id") or str(uuid4())
            attempt = int(inputs.get("attempt", 0))
            node_key = inputs.get("node", "?")

            async with SessionLocal() as s:
                # 1) Idempotency: aynı exec_id daha önce success ise cache döndür
                existing = (await s.execute(
                    select(ToolInvocation).where(ToolInvocation.exec_id == exec_id)
                )).scalars().first()
                if existing and existing.status == "success":
                    await _publish_ok(task, existing.result or {}, exec_id)
                    print(f"[tool] idempotent cache hit exec_id={exec_id} tool={tool}")
                    return

                # 2) Fault injection (test)
                if attempt < int(inputs.get("fail_times", 0)):
                    await _record_fail(s, exec_id, task.trace_id, node_key, tool, args, attempt,
                                       "TRANSIENT", "injected")
                    await _publish_fail(task, "TRANSIENT", f"injected tool fail attempt={attempt}")
                    return

                # 3) Permission + catalog
                spec = (catalog.get("tools") or {}).get(tool)
                if spec is None or spec.get("permission") not in allow:
                    await _record_fail(s, exec_id, task.trace_id, node_key, tool, args, attempt,
                                       "PERMISSION", f"tool '{tool}' not permitted")
                    await _publish_fail(task, "PERMISSION", f"tool '{tool}' not permitted")
                    print(f"[tool] PERMISSION deny tool={tool}")
                    return
                handler = HANDLERS.get(tool)
                if handler is None:
                    await _record_fail(s, exec_id, task.trace_id, node_key, tool, args, attempt,
                                       "SCHEMA", f"no handler for '{tool}'")
                    await _publish_fail(task, "SCHEMA", f"no handler for '{tool}'")
                    return

                # 4) Dry-run — yan etki yok, simüle sonuç (INV-2)
                dry_run = bool(inputs.get("dry_run", False))
                if dry_run:
                    sim_result = handler(args) if handler else {}
                    sim_result["_simulated"] = True
                    await _record_success(s, exec_id, task.trace_id, node_key, tool, args, attempt,
                                          sim_result, catalog, dry_run=True)
                    await _publish_ok(task, sim_result, exec_id, dry_run=True)
                    print(f"[tool] dry-run ✓ {tool} exec_id={exec_id} node={node_key}")
                    return

                # 5) Schema validation — INV-3
                schema_errors = schema_validator.validate(tool, args, catalog)
                if schema_errors:
                    await _record_fail(s, exec_id, task.trace_id, node_key, tool, args, attempt,
                                       "SCHEMA", f"schema errors: {'; '.join(schema_errors)}")
                    await _publish_fail(task, "SCHEMA", f"schema errors: {'; '.join(schema_errors)}")
                    print(f"[tool] SCHEMA error exec_id={exec_id} tool={tool}: {schema_errors}")
                    return

                # 6) Rate limit — INV-5
                allowed, retry_after = await rate_limiter.check(tool, task.trace_id, spec, redis)
                if not allowed:
                    await _record_fail(s, exec_id, task.trace_id, node_key, tool, args, attempt,
                                       "RATE_LIMIT", f"rate limited retry_after={retry_after}")
                    await _publish_fail(task, "RATE_LIMIT", f"rate limited", retry_after=retry_after)
                    print(f"[tool] RATE_LIMIT exec_id={exec_id} tool={tool} retry_after={retry_after}")
                    return

                # 7) Execute (timeout)
                timeout = spec.get("timeout_ms", 15000) / 1000
                try:
                    result = await asyncio.wait_for(asyncio.to_thread(handler, args), timeout=timeout)
                except asyncio.TimeoutError:
                    await _record_fail(s, exec_id, task.trace_id, node_key, tool, args, attempt,
                                       "TIMEOUT", "tool timeout")
                    await _publish_fail(task, "TIMEOUT", "tool timeout")
                    return

                # 8) Atomic success + compensation (INV-1)
                await _record_success(s, exec_id, task.trace_id, node_key, tool, args, attempt,
                                      result, catalog)
                await _publish_ok(task, result, exec_id)
                print(f"[tool] ✓ {tool} exec_id={exec_id} node={node_key}")
        except Exception as e:  # noqa: BLE001
            print(f"[tool] ✗ hata: {e}")
            try:
                env = json.loads(msg.data)
                await _publish_fail(TaskMessage.model_validate(env), "UNKNOWN", str(e))
            except Exception:  # noqa: BLE001
                pass
        finally:
            await msg.ack()

    for _ in range(60):
        try:
            await js.subscribe(Subject.TOOL_REQUEST.value, durable=DURABLE, cb=handle, manual_ack=True)
            print(f"✓ tool-runtime dinliyor: {Subject.TOOL_REQUEST.value}")
            break
        except Exception:
            await asyncio.sleep(2)
    while True:
        await asyncio.sleep(3600)


async def _record_success(s, exec_id, trace_id, node_key, tool, args, attempt,
                           result, catalog, *,
                           dry_run=False, rate_limited=False, schema_errors=None):
    """Atomic: tool_invocations.status=success + compensation (INV-1)."""
    vals = dict(id=str(uuid4()), task_id=str(trace_id), node_key=node_key, tool=tool, args=args,
                exec_id=exec_id, attempt=attempt, status="success", result=result,
                dry_run=dry_run, rate_limited=rate_limited, schema_errors=schema_errors,
                finished_at=_now())
    stmt = pg_insert(ToolInvocation).values(**vals).on_conflict_do_update(
        index_elements=["exec_id"],
        set_={"status": "success", "result": result, "dry_run": dry_run,
              "rate_limited": rate_limited, "schema_errors": schema_errors, "finished_at": _now()},
    )
    await s.execute(stmt)
    if not dry_run:  # INV-2: dry-run → compensation kaydı YOK
        await compensator.record_if_needed(s, exec_id, str(trace_id), node_key, tool, args, catalog)
    await s.commit()


async def _record_fail(s, exec_id, trace_id, node_key, tool, args, attempt,
                        error_code, error, *,
                        schema_errors=None):
    """exec_id ile idempotent insert (hata durumu)."""
    vals = dict(id=str(uuid4()), task_id=str(trace_id), node_key=node_key, tool=tool, args=args,
                exec_id=exec_id, attempt=attempt, status="failed",
                error_code=error_code, error=error,
                dry_run=False, rate_limited=(error_code == "RATE_LIMIT"),
                schema_errors=schema_errors, finished_at=_now())
    stmt = pg_insert(ToolInvocation).values(**vals).on_conflict_do_update(
        index_elements=["exec_id"],
        set_={"status": "failed", "error_code": error_code, "error": error,
              "rate_limited": (error_code == "RATE_LIMIT"), "finished_at": _now()},
    )
    await s.execute(stmt)
    await s.commit()


if __name__ == "__main__":
    asyncio.run(run())
