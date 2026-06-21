"""Preview HTTP API — v2.3 Live Preview (port 8005; canlı app host 8100'de).

Tek-slot in-memory canlı dev server yöneticisi. DB yok.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Query

from . import manager

app = FastAPI(title="Preview API", version="2.3.0")
PUBLIC_URL = os.environ.get("PREVIEW_PUBLIC_URL", "http://localhost:8100")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "preview"}


# NOT: statik route'lar (/preview/stop, /preview/status) {build_id} ÖNCESİNDE tanımlanmalı —
# aksi halde "stop" bir build_id olarak eşleşir (FastAPI sıralı route match).
@app.get("/preview/status")
async def status() -> dict:
    return manager.status()


@app.post("/preview/stop")
async def stop() -> dict:
    import asyncio
    return await asyncio.to_thread(manager.stop)


@app.post("/preview/{build_id}")
async def start(build_id: str) -> dict:
    import asyncio
    return await asyncio.to_thread(manager.start, build_id, PUBLIC_URL)
