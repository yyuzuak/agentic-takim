"""Durable execution kanıtı — interrupt + cross-process resume.

hello-graph `execute` düğümünden ÖNCE durdurulur (interrupt_before). Ara durum
Postgres'e checkpoint olarak yazılır. Container kill + restart sonrası `resume`,
kalıcı durumu okuyup kaldığı yerden tamamlar — yani yürütme süreçler arası dayanıklı.

Kullanım (container içinde):
  python -m runner.resume_demo start  <thread_id>
  python -m runner.resume_demo resume <thread_id>
"""
from __future__ import annotations

import asyncio
import os
import sys

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from .graph import build_graph

DB_DSN = os.environ.get("DATABASE_URL", "postgresql://agentic:agentic_dev_pw@postgres:5432/agentic_os")
DB_DSN = DB_DSN.replace("+asyncpg", "").replace("postgresql+psycopg", "postgresql")


async def run(cmd: str, thread_id: str) -> None:
    async with AsyncPostgresSaver.from_conn_string(DB_DSN) as cp:
        await cp.setup()
        graph = build_graph().compile(checkpointer=cp, interrupt_before=["execute"])
        cfg = {"configurable": {"thread_id": thread_id}}

        if cmd == "start":
            await graph.ainvoke({"goal": "durable demo", "steps": []}, cfg)
            st = await graph.aget_state(cfg)
            print(f"⏸  interrupt: steps={st.values['steps']} next={st.next}")
            print("   ara durum Postgres'e yazıldı. Container'ı kill edip 'resume' çalıştırın.")

        elif cmd == "resume":
            st = await graph.aget_state(cfg)
            if not st.values:
                print(f"✗ thread '{thread_id}' için kalıcı durum yok. Önce 'start' çalıştırın.")
                sys.exit(1)
            print(f"↻  kalıcı durumdan devam: steps={st.values.get('steps')} next={st.next}")
            await graph.ainvoke(None, cfg)  # None = checkpoint'ten devam
            st2 = await graph.aget_state(cfg)
            print(f"✓  tamamlandı: steps={st2.values['steps']} next={st2.next}")

        else:
            print(f"✗ bilinmeyen komut: {cmd} (start|resume)")
            sys.exit(2)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("kullanım: python -m runner.resume_demo <start|resume> <thread_id>")
        sys.exit(2)
    asyncio.run(run(sys.argv[1], sys.argv[2]))
