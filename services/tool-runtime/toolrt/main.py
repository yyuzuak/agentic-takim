"""Tool Runtime — ACP.TOOL.REQUEST tüketir, izinli/idempotent/timeout'lu çalıştırır,
ACP.TOOL.RESULT'a yazar. Yan etki at-most-once (exec_id idempotency)."""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import nats
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from agentic_schemas.acp.v1 import ErrorCode, ErrorMessage, ResultMessage, ResultPayload, TaskMessage
from agentic_schemas.events.v1 import Subject

from .db import SessionLocal, ToolInvocation
from .tools import HANDLERS, load_catalog

NATS_URL = os.environ.get("NATS_URL", "nats://nats:4222")
DURABLE = "tool-runtime"
NON_RETRYABLE = {"PERMISSION", "SCHEMA"}


def _now():
    return datetime.now(timezone.utc)


async def run() -> None:
    nc = await nats.connect(NATS_URL, name="tool-runtime", reconnect_time_wait=2, max_reconnect_attempts=-1)
    js = nc.jetstream()
    catalog = load_catalog()
    allow = set(catalog.get("permissions", {}).get("allow", []))

    async def _publish_ok(task: TaskMessage, result: dict, exec_id: str) -> None:
        msg = ResultMessage(from_agent="tool-runtime", to_agent="kaptan", trace_id=task.trace_id,
                            in_reply_to=task.message_id, skill=task.skill, timestamp=int(time.time()),
                            payload=ResultPayload(result={**result, "exec_id": exec_id}, confidence=1.0))
        await js.publish(Subject.TOOL_RESULT.value, msg.model_dump_json(by_alias=True).encode())

    async def _publish_fail(task: TaskMessage, code: str, message: str) -> None:
        err = ErrorMessage(from_agent="tool-runtime", to_agent="kaptan", trace_id=task.trace_id,
                           in_reply_to=task.message_id, timestamp=int(time.time()),
                           error_code=ErrorCode(code) if code in ErrorCode.__members__ else ErrorCode.UNKNOWN,
                           message=message)
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
                # Idempotency: aynı exec_id daha önce success ise cache döndür (re-exec YOK)
                existing = (await s.execute(
                    select(ToolInvocation).where(ToolInvocation.exec_id == exec_id)
                )).scalars().first()
                if existing and existing.status == "success":
                    await _publish_ok(task, existing.result or {}, exec_id)
                    print(f"[tool] idempotent cache hit exec_id={exec_id} tool={tool}")
                    return

                # Fault injection (test): attempt < fail_times → TRANSIENT
                if attempt < int(inputs.get("fail_times", 0)):
                    await _record(s, exec_id, task.trace_id, node_key, tool, args, attempt, "failed",
                                  error_code="TRANSIENT", error="injected")
                    await _publish_fail(task, "TRANSIENT", f"injected tool fail attempt={attempt}")
                    return

                # Permission + catalog
                spec = (catalog.get("tools") or {}).get(tool)
                if spec is None or spec.get("permission") not in allow:
                    await _record(s, exec_id, task.trace_id, node_key, tool, args, attempt, "failed",
                                  error_code="PERMISSION", error=f"tool '{tool}' not permitted")
                    await _publish_fail(task, "PERMISSION", f"tool '{tool}' not permitted")
                    print(f"[tool] PERMISSION deny tool={tool}")
                    return
                handler = HANDLERS.get(tool)
                if handler is None:
                    await _record(s, exec_id, task.trace_id, node_key, tool, args, attempt, "failed",
                                  error_code="SCHEMA", error=f"no handler for '{tool}'")
                    await _publish_fail(task, "SCHEMA", f"no handler for '{tool}'")
                    return

                # Execute (timeout'lu, thread'de — handler senkron)
                timeout = spec.get("timeout_ms", 15000) / 1000
                try:
                    result = await asyncio.wait_for(asyncio.to_thread(handler, args), timeout=timeout)
                except asyncio.TimeoutError:
                    await _record(s, exec_id, task.trace_id, node_key, tool, args, attempt, "failed",
                                  error_code="TIMEOUT", error="tool timeout")
                    await _publish_fail(task, "TIMEOUT", "tool timeout")
                    return

                await _record(s, exec_id, task.trace_id, node_key, tool, args, attempt, "success", result=result)
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


async def _record(s, exec_id, trace_id, node_key, tool, args, attempt, status, result=None, error_code=None, error=None):
    """exec_id ile idempotent insert (ON CONFLICT DO UPDATE → son durum)."""
    vals = dict(id=str(uuid4()), task_id=str(trace_id), node_key=node_key, tool=tool, args=args,
                exec_id=exec_id, attempt=attempt, status=status, result=result,
                error_code=error_code, error=error, finished_at=_now())
    stmt = pg_insert(ToolInvocation).values(**vals).on_conflict_do_update(
        index_elements=["exec_id"],
        set_={"status": status, "result": result, "error_code": error_code, "error": error, "finished_at": _now()},
    )
    await s.execute(stmt)
    await s.commit()


if __name__ == "__main__":
    asyncio.run(run())
