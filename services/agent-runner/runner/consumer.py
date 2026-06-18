"""ACP task tüketicisi — ACP.TASK.CREATED'ı işler, sonucu COMPLETED/FAILED'a yazar.

LangGraph graph'ı AsyncPostgresSaver ile çalışır (durable; thread_id = trace_id).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from uuid import UUID

import nats
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agentic_schemas.acp.v1 import ErrorCode, ErrorMessage, ResultMessage, ResultPayload, TaskMessage
from agentic_schemas.events.v1 import Subject

from .graph import build_graph

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

        async def handle(msg) -> None:
            try:
                task = TaskMessage.model_validate(json.loads(msg.data))
                trace_id = str(task.trace_id)
                # thread_id node başına benzersiz olmalı (message_id); aksi halde aynı
                # workflow'un düğümleri checkpoint thread'ini paylaşır ve resume eder.
                thread_id = str(task.message_id)
                state = await graph.ainvoke(
                    {"goal": task.payload.goal, "steps": []},
                    {"configurable": {"thread_id": thread_id}},
                )
                result = ResultMessage(
                    from_agent=task.to_agent,
                    to_agent="kaptan",
                    trace_id=task.trace_id,
                    in_reply_to=task.message_id,
                    skill=task.skill,
                    timestamp=int(time.time()),
                    payload=ResultPayload(result={"steps": state["steps"]}, confidence=1.0),
                )
                await js.publish(Subject.TASK_COMPLETED.value, result.model_dump_json(by_alias=True).encode())
                print(f"[agent-runner] ✓ tamamlandı trace={trace_id} agent={task.to_agent}")
            except Exception as e:  # noqa: BLE001
                print(f"[agent-runner] ✗ hata: {e}")
                try:
                    env = json.loads(msg.data)
                    err = ErrorMessage(
                        from_agent="agent-runner",
                        to_agent="kaptan",
                        trace_id=UUID(env["trace_id"]),
                        timestamp=int(time.time()),
                        error_code=ErrorCode.LOGICAL,
                        message=str(e),
                    )
                    await js.publish(Subject.TASK_FAILED.value, err.model_dump_json(by_alias=True).encode())
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
