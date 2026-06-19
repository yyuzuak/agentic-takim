"""Tool-runtime HTTP API — v1.1-b

NATS consumer + HTTP API birlikte çalışır.
Endpoints: /health, /health/adapters, /tools/capabilities, /compensations/{exec_id}/apply
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from .tools import build_registry, load_catalog


_registry: dict = {}
_catalog: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _registry, _catalog
    _catalog = load_catalog()
    _registry = build_registry(_catalog)
    # NATS consumer arka planda başlatılır — registry paylaşılır
    from . import main as _main
    asyncio.create_task(_main.run(registry=_registry))
    yield


app = FastAPI(title="Tool Runtime API", version="1.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "tool-runtime", "adapters": len(_registry)}


@app.get("/health/adapters")
async def health_adapters() -> dict:
    results = []
    for name, adapter in _registry.items():
        try:
            h = await adapter.healthcheck()
            results.append(h.dict())
        except Exception as e:
            results.append({"adapter": name, "status": "down", "latency_ms": None, "detail": str(e)})
    return {"adapters": results}


@app.get("/tools/capabilities")
async def tool_capabilities() -> dict:
    tools: dict = {}
    for name, adapter in _registry.items():
        caps = adapter.capabilities()
        caps["circuit_breaker"] = True  # tüm adapter'lar CB ile wrap edilir (v1.1-c)
        tools[name] = caps
    return {"tools": tools}


class ApplyIn(BaseModel):
    actor: str = "anonymous"


@app.post("/compensations/{exec_id}/apply")
async def apply_compensation(exec_id: str, body: ApplyIn) -> dict:
    from .compensator import apply as comp_apply
    from .db import SessionLocal
    async with SessionLocal() as s:
        result = await comp_apply(s, exec_id, _registry, actor=body.actor)
    return result
