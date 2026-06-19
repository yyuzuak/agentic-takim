"""Memory-aware planning — recall (v0.8).

İlke: memory planner'a DANIŞMANLIK yapar, DAG üretmez. Postgres=source of truth
(memory_entries), Qdrant=retrieval index (task_memory). Yalnız başarılı görevler.
Embedding: API key yoksa deterministik local (feature-hashing); varsa LiteLLM.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import update

from .config import settings
from .models import MemoryEntry

DIM = 1536
COLLECTION = "task_memory"
TOP_K = 5
MAX_PER_TAG = 2
MAX_MEMORY_CONTEXT = 3
LOCAL_MIN_SCORE = 0.78
OPENAI_MIN_SCORE = 0.85
_NS = uuid.UUID("00000000-0000-0000-0000-00000000ace0")


def _point_id(task_id: str) -> str:
    return str(uuid.uuid5(_NS, task_id))  # deterministik → re-store overwrite (idempotent)


def _local_embed(text: str) -> list[float]:
    v = [0.0] * DIM
    for tok in re.findall(r"\w+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


async def _litellm_embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{settings.litellm_url}/v1/embeddings",
                         headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                         json={"model": settings.llm_model_embed if hasattr(settings, "llm_model_embed") else "text-embedding-3-small",
                               "input": text})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


async def embed(text: str) -> tuple[list[float], str]:
    """(vector, provider) — provider local|openai."""
    if settings.llm_available and os.getenv("USE_LLM_EMBED", "0") == "1":
        try:
            return await _litellm_embed(text), "openai"
        except Exception:  # noqa: BLE001 — fallback
            pass
    return _local_embed(text), "local"


def _min_score(provider: str) -> float:
    return OPENAI_MIN_SCORE if provider == "openai" else LOCAL_MIN_SCORE


async def ensure_collection() -> None:
    try:
        async with httpx.AsyncClient(base_url=settings.qdrant_url, timeout=10) as c:
            r = await c.get(f"/collections/{COLLECTION}")
            if r.status_code == 200:
                return
            await c.put(f"/collections/{COLLECTION}", json={"vectors": {"size": DIM, "distance": "Cosine"}})
    except Exception as e:  # noqa: BLE001
        print(f"[memory] ensure_collection hata: {e}", flush=True)


async def store(s, task, snapshot: dict, parent_memory_ids: list | None = None) -> None:
    """Two-phase: (1) memory_entries pending, (2) Qdrant upsert, (3) status=indexed.
    Yalnız outcome=done. Idempotent (UNIQUE task_id + sabit point id)."""
    if not settings.memory_available or task.status != "done":
        return
    inputs = task.inputs or {}
    wf_type = inputs.get("_workflow_type") or "build"
    plan_summary = [{"key": n.get("key"), "role": n.get("role"), "skill": n.get("skill")} for n in (task.plan or [])]
    decisions = (snapshot or {}).get("shared", {}).get("decisions", [])
    refinements = (snapshot or {}).get("refinements", {})
    rsum = None
    if refinements:
        grp = next(iter(refinements.values()))
        rsum = {"iterations": len(grp), "terminal_reason": grp[-1].get("decision"),
                "best_score": max((g.get("score") or 0) for g in grp)}
    vector, provider = await embed(task.goal)

    # (1) pending insert (idempotent)
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    mem_id = str(uuid.uuid4())
    res = await s.execute(
        pg_insert(MemoryEntry).values(
            id=mem_id, task_id=task.id, goal=task.goal,
            summary=f"{wf_type}: {len(plan_summary)} adım, {len(decisions)} karar",
            outcome="done", plan=task.plan, tags=[wf_type], workflow_type=wf_type,
            planner_source=inputs.get("_planner_source"), success_score=1.0,
            refinement_summary=rsum, status="pending", provider=provider,
            parent_memory_ids=parent_memory_ids or [],
        ).on_conflict_do_nothing(index_elements=["task_id"])
    )
    await s.flush()
    if res.rowcount == 0:
        return  # zaten var (idempotent)

    # (2) Qdrant upsert
    try:
        async with httpx.AsyncClient(base_url=settings.qdrant_url, timeout=15) as c:
            await ensure_collection()
            payload = {"task_id": task.id, "goal": task.goal, "outcome": "done",
                       "workflow_type": wf_type, "plan": task.plan, "summary": f"{wf_type} workflow"}
            rr = await c.put(f"/collections/{COLLECTION}/points?wait=true",
                             json={"points": [{"id": _point_id(task.id), "vector": vector, "payload": payload}]})
            rr.raise_for_status()
        # (3) indexed
        await s.execute(update(MemoryEntry).where(MemoryEntry.task_id == task.id).values(status="indexed"))
        print(f"[memory] stored task={task.id} type={wf_type} provider={provider}", flush=True)
    except Exception as e:  # noqa: BLE001 — index fail → pending kalır (repair v0.8.1)
        print(f"[memory] qdrant upsert fail (status=pending): {e}", flush=True)


def _family(t: str | None) -> str:
    return t or "build"


async def recall(s, goal: str, inferred_type: str) -> dict:
    """{hits, avg_score, confidence}. Guardrails: MIN_SCORE, TOP_K, diversity, drift."""
    if not settings.memory_available:
        return {"hits": [], "avg_score": 0.0, "confidence": "low"}
    vector, provider = await embed(goal)
    try:
        async with httpx.AsyncClient(base_url=settings.qdrant_url, timeout=10) as c:
            r = await c.post(f"/collections/{COLLECTION}/points/search",
                             json={"vector": vector, "limit": TOP_K, "with_payload": True,
                                   "score_threshold": _min_score(provider)})
            if r.status_code != 200:
                return {"hits": [], "avg_score": 0.0, "confidence": "low"}
            raw = r.json().get("result", [])
    except Exception:  # noqa: BLE001
        return {"hits": [], "avg_score": 0.0, "confidence": "low"}

    hits = [{"id": h["id"], "score": h["score"], **(h.get("payload") or {})} for h in raw]
    # diversity: unique workflow_type first, sonra skor
    seen_types: dict[str, int] = {}
    diverse: list[dict] = []
    for h in sorted(hits, key=lambda x: -x["score"]):
        t = h.get("workflow_type", "build")
        if seen_types.get(t, 0) >= MAX_PER_TAG:
            continue
        seen_types[t] = seen_types.get(t, 0) + 1
        diverse.append(h)
    # unique-type-first re-rank, sonra MAX_MEMORY_CONTEXT
    diverse.sort(key=lambda x: (list(seen_types).index(x.get("workflow_type", "build")), -x["score"]))
    selected = diverse[:MAX_MEMORY_CONTEXT]

    avg = round(sum(h["score"] for h in selected) / len(selected), 4) if selected else 0.0
    confidence = "high" if avg >= 0.90 else "medium" if avg >= 0.85 else "low"
    # drift guard: top hit type, inferred ailesinde değilse bir kademe düş
    if selected and _family(selected[0].get("workflow_type")) != _family(inferred_type):
        confidence = {"high": "medium", "medium": "low", "low": "low"}[confidence]

    # retrieval_count++ (recall edilenler)
    if selected:
        await s.execute(
            update(MemoryEntry).where(MemoryEntry.task_id.in_([h["task_id"] for h in selected]))
            .values(retrieval_count=MemoryEntry.retrieval_count + 1)
        )
    return {"hits": selected, "avg_score": avg, "confidence": confidence}


async def mark_reuse_success(s, memory_ids: list[str]) -> None:
    if not memory_ids:
        return
    await s.execute(
        update(MemoryEntry).where(MemoryEntry.task_id.in_(memory_ids))
        .values(reuse_success_count=MemoryEntry.reuse_success_count + 1)
    )
