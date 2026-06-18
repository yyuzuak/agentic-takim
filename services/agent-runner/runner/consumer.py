"""ACP task tüketicisi — ACP.TASK.CREATED'ı işler, sonucu COMPLETED/FAILED'a yazar.

LangGraph graph'ı AsyncPostgresSaver ile çalışır (durable; thread_id = trace_id).
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time

import nats
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agentic_schemas.acp.v1 import ErrorCode, ErrorMessage, ResultMessage, ResultPayload, TaskMessage
from agentic_schemas.events.v1 import Subject

from .graph import build_graph


def _artifact_content(snapshot: dict, agent: str, node_key: str) -> dict | None:
    return (snapshot.get("agents", {}).get(agent, {}).get("artifacts", {}).get(node_key) or {}).get("content")


def _collaborate(task) -> list[dict]:
    """role→handler. Deterministik stub; LLM yok (v0.4 kısıtı). Üretilen context event'leri döner.

    - producer: artifact.created (draft)
    - critic:  producer'ı DEĞİŞTİRMEZ, critique üretir
    - synthesizer: producer artifact'ları + critique'leri birleştirir → consensus + decision
    """
    p = task.payload
    role, agent, goal = p.node_role, task.to_agent, p.goal
    snapshot, history = p.snapshot or {}, p.node_history or []

    if role == "critic":
        events = []
        for dep in history:
            content = _artifact_content(snapshot, dep["agent"], dep["node_key"])
            if content is None:
                continue
            events.append({"type": "critique", "agent": agent, "payload": {
                "target_node": dep["node_key"], "score": 0.8,
                "issues": [f"{dep['node_key']} taslağı gözden geçirildi"],
                "suggestions": [f"{agent}: netlik ve kapsam iyileştirilebilir"],
            }})
        return events

    if role == "synthesizer":
        drafts = {d["node_key"]: _artifact_content(snapshot, d["agent"], d["node_key"]) for d in history}
        critiques = [c for a in snapshot.get("agents", {}).values() for c in a.get("critiques", [])]
        consensus = {"text": f"consensus({goal})", "from_drafts": [k for k, v in drafts.items() if v],
                     "critique_count": len(critiques)}
        return [
            {"type": "artifact.created", "agent": agent, "payload": {"kind": "consensus", "content": consensus}},
            {"type": "decision.made", "agent": agent, "payload": {"decision": f"{agent} nihai çıktıyı sentezledi"}},
        ]

    # producer (varsayılan)
    return [{"type": "artifact.created", "agent": agent, "payload": {
        "kind": "draft", "content": {"text": f"{task.skill} draft for: {goal}"}}}]

NATS_URL = os.environ.get("NATS_URL", "nats://nats:4222")
DB_DSN = os.environ.get("DATABASE_URL", "postgresql://agentic:agentic_dev_pw@postgres:5432/agentic_os")
DB_DSN = DB_DSN.replace("+asyncpg", "").replace("postgresql+psycopg", "postgresql")
DURABLE = "agent-runner-tasks"


async def run() -> None:
    nc = await nats.connect(NATS_URL, name="agent-runner", reconnect_time_wait=2, max_reconnect_attempts=-1)
    js = nc.jetstream()

    async with AsyncPostgresSaver.from_conn_string(DB_DSN) as cp:
        await cp.setup()
        graph = build_graph().compile(checkpointer=cp)

        async def _publish_failed(task: TaskMessage, code: ErrorCode, message: str) -> None:
            err = ErrorMessage(
                from_agent="agent-runner", to_agent="kaptan", trace_id=task.trace_id,
                in_reply_to=task.message_id, timestamp=int(time.time()), error_code=code, message=message,
            )
            await js.publish(Subject.TASK_FAILED.value, err.model_dump_json(by_alias=True).encode())

        def _should_inject_fail(inputs: dict) -> ErrorCode | None:
            """Test aracı: fail_node (hedef düğüm) / fail_times / fail_at_attempt / fail_percentage."""
            target = inputs.get("fail_node")
            if target is not None and target != inputs.get("node"):
                return None  # bu düğüm hedef değil
            attempt = int(inputs.get("attempt", 0))
            code_str = inputs.get("fail_code", "TRANSIENT")
            trigger = (
                attempt < int(inputs.get("fail_times", 0))
                or (inputs.get("fail_at_attempt") is not None and attempt == int(inputs["fail_at_attempt"]))
                or (inputs.get("fail_percentage") and random.random() < float(inputs["fail_percentage"]))
            )
            if not trigger:
                return None
            try:
                return ErrorCode(code_str)
            except ValueError:
                return ErrorCode.TRANSIENT

        async def handle(msg) -> None:
            try:
                task = TaskMessage.model_validate(json.loads(msg.data))
                trace_id = str(task.trace_id)
                inputs = task.payload.inputs or {}

                # Fault injection (kontrollü hata — retry/DLQ testleri için)
                inject = _should_inject_fail(inputs)
                if inject is not None:
                    await _publish_failed(task, inject, f"injected failure ({inject.value}) attempt={inputs.get('attempt', 0)}")
                    print(f"[agent-runner] ⚠ injected fail trace={trace_id} code={inject.value}")
                    await msg.ack()
                    return

                # thread_id node başına benzersiz (message_id) — checkpoint izolasyonu
                state = await graph.ainvoke(
                    {"goal": task.payload.goal, "steps": []},
                    {"configurable": {"thread_id": str(task.message_id)}},
                )
                events = _collaborate(task)  # role→handler: producer/critic/synthesizer
                result = ResultMessage(
                    from_agent=task.to_agent, to_agent="kaptan", trace_id=task.trace_id,
                    in_reply_to=task.message_id, skill=task.skill, timestamp=int(time.time()),
                    payload=ResultPayload(result={"steps": state["steps"], "exec_id": inputs.get("exec_id")},
                                          confidence=1.0, events=events),
                )
                await js.publish(Subject.TASK_COMPLETED.value, result.model_dump_json(by_alias=True).encode())
                print(f"[agent-runner] ✓ tamamlandı trace={trace_id} agent={task.to_agent}")
            except Exception as e:  # noqa: BLE001 — gerçek (injection değil) hata
                print(f"[agent-runner] ✗ hata: {e}")
                try:
                    env = json.loads(msg.data)
                    await _publish_failed(
                        TaskMessage.model_validate(env), ErrorCode.UNKNOWN, str(e)
                    )
                except Exception:  # noqa: BLE001
                    pass
            finally:
                await msg.ack()

        # Stream'ler init-nats ile sonradan oluşabilir; oluşana kadar retry.
        for _ in range(60):
            try:
                await js.subscribe(Subject.TASK_CREATED.value, durable=DURABLE, cb=handle, manual_ack=True)
                print(f"✓ agent-runner dinliyor: {Subject.TASK_CREATED.value}")
                break
            except Exception:
                await asyncio.sleep(2)
        else:
            print("! agent-runner abone olamadı (stream yok?).")

        while True:
            await asyncio.sleep(3600)
