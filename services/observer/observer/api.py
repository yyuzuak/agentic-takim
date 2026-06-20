"""Observer HTTP API — v1.3 (port 8002, sidecar analytics plane).

Endpoints: /health /scores /clusters /recommendations /raw
Service auth: X-Internal-Token (control-plane proxy enjekte eder). /health hariç.
Tüm cache'li endpoint'ler 30s TTL. /raw cache bypass (debug).
"""
from __future__ import annotations

import os
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from . import SPEC_HASH, SPEC_VERSION
from .aggregator import compute_kpis
from .cache import cached
from .clusterer import compute_clusters
from .db import SessionLocal
from .recommender import compute_recommendations
from .scorer import compute_scores

INTERNAL_TOKEN = os.environ.get("OBSERVER_INTERNAL_TOKEN", "dev-internal-token")

app = FastAPI(title="Observer API", version=SPEC_VERSION)

Window = Literal["1h", "24h", "7d"]


async def require_token(x_internal_token: str | None = Header(default=None)) -> None:
    """INVARIANT: dış erişim engellenir. /health bunu kullanmaz."""
    if x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="invalid internal token")


@app.get("/health")
async def health() -> dict:
    db_ok = "connected"
    try:
        from sqlalchemy import text
        async with SessionLocal() as s:
            await s.execute(text("SELECT 1"))
    except Exception as e:  # pragma: no cover
        db_ok = f"error: {e}"
    return {"status": "ok", "service": "observer", "spec": SPEC_VERSION,
            "spec_hash": SPEC_HASH[:12], "db": db_ok}


@app.get("/scores", dependencies=[Depends(require_token)])
async def scores(window: Window = Query(default="24h")) -> dict:
    async def produce():
        async with SessionLocal() as s:
            return await compute_scores(s, window)
    return await cached("scores", {"window": window}, produce)


@app.get("/clusters", dependencies=[Depends(require_token)])
async def clusters(window: Window = Query(default="24h")) -> dict:
    async def produce():
        async with SessionLocal() as s:
            return {"clusters": await compute_clusters(s, window), "window": window}
    return await cached("clusters", {"window": window}, produce)


@app.get("/recommendations", dependencies=[Depends(require_token)])
async def recommendations(window: Window = Query(default="24h")) -> dict:
    async def produce():
        async with SessionLocal() as s:
            return {"recommendations": await compute_recommendations(s, window), "window": window}
    return await cached("recommendations", {"window": window}, produce)


@app.get("/raw", dependencies=[Depends(require_token)])
async def raw(window: Window = Query(default="24h")) -> dict:
    """Debug — cache bypass, ham KPI agregasyonu."""
    async with SessionLocal() as s:
        return await compute_kpis(s, window)
