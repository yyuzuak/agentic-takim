"""Agent-runner giriş noktası.

Başlangıçta:
  1. AsyncPostgresSaver checkpointer tablolarını kurar (.setup()).
  2. hello-graph'ı bir kez çalıştırır (kurulum kanıtı, decision trace loglanır).
  3. Açık kalır (ileride NATS'tan task tüketecek).

Durable execution testi (manuel):
  - graph'ı çalıştır → container'ı `docker kill` et → `up` → checkpointer'dan resume.
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from .graph import build_graph

# AsyncPostgresSaver psycopg (sync DSN) bekler; asyncpg sürücüsünü çıkar.
DB_DSN = os.environ.get("DATABASE_URL", "postgresql://agentic:agentic_dev_pw@postgres:5432/agentic_os")
DB_DSN = DB_DSN.replace("+asyncpg", "").replace("postgresql+psycopg", "postgresql")


async def main() -> None:
    async with AsyncPostgresSaver.from_conn_string(DB_DSN) as checkpointer:
        await checkpointer.setup()
        graph = build_graph().compile(checkpointer=checkpointer)

        thread_id = str(uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        result = await graph.ainvoke({"goal": "kurulum kanıtı", "steps": []}, config)

        print(f"✓ agent-runner hazır. hello-graph çalıştı (thread={thread_id}).")
        print(f"  decision trace: {result['steps']}")

        # Açık kal (ileride NATS task tüketimi buraya gelecek).
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
