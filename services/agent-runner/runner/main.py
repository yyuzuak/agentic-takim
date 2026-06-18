"""Agent-runner giriş noktası — ACP task tüketicisini çalıştırır.

Yürütme LangGraph + AsyncPostgresSaver ile durable'dır (thread_id = trace_id).
Durable resume demosu için: `python -m runner.resume_demo start|resume <thread_id>`.
"""
from __future__ import annotations

import asyncio

from .consumer import run

if __name__ == "__main__":
    asyncio.run(run())
