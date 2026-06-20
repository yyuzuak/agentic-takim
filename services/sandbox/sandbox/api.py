"""Sandbox HTTP API — v2.2 Build Execution (port 8004).

Stateless executor: build'i çalıştırır, sonuç döner. DB YOK (control-plane persist eder).
"""
from __future__ import annotations

from fastapi import FastAPI

from . import runner

app = FastAPI(title="Sandbox API", version="2.2.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "sandbox"}


@app.post("/run/{build_id}")
async def run(build_id: str) -> dict:
    # subprocess bloklayıcı → thread pool'da çalıştır (event loop'u tıkamasın)
    import anyio
    return await anyio.to_thread.run_sync(runner.run_build, build_id)
