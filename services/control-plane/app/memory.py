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

# v0.8.1 consolidation sabitleri (tunable)
HALFLIFE_DAYS = 14.0          # decay yarı-ömrü
DEDUP_LOCAL = 0.97            # store-time near-dup eşiği (lokal embedding)
DEDUP_OPENAI = 0.93
RANK_ALPHA = 0.7             # recall: similarity ağırlığı
RANK_BETA = 0.3             # recall: value_score ağırlığı
KEEP_PER_TYPE = 20           # forgetting: workflow_type başına tutulan
MIN_AGE_DAYS = 7             # bundan eski + kullanılmamış + düşük → evict
FORGET_THRESHOLD = 0.25
MAX_MEMORIES = 500           # global cap


def compute_value(reuse_success_count: int, retrieval_count: int,
                  created_at, refinement_summary: dict | None, now=None) -> float:
    """Bileşik değer (0-1): reuse + recency(decay) + retrieval + refine."""
    now = now or datetime.now(timezone.utc)
    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0) if created_at else 0.0
    recency = math.exp(-age_days / HALFLIFE_DAYS)
    reuse = math.tanh((reuse_success_count or 0) / 3.0)
    retr = math.tanh((retrieval_count or 0) / 5.0)
    refine = float((refinement_summary or {}).get("best_score") or 0.0)
    val = 0.40 * reuse + 0.30 * recency + 0.15 * retr + 0.15 * refine
    return round(max(0.0, min(1.0, val)), 4)


def _dedup_threshold(provider: str) -> float:
    return DEDUP_OPENAI if provider == "openai" else DEDUP_LOCAL


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

    # (0) store-time DEDUP: aynı workflow_type'ta near-dup varsa yeni entry açma → reinforce
    dup_task = await _find_near_dup(vector, provider, wf_type, exclude_task=task.id)
    if dup_task:
        await _reinforce(s, dup_task)
        print(f"[memory] dedup: task={task.id} ~ {dup_task} (reinforce, yeni entry yok)", flush=True)
        return

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


async def _find_near_dup(vector: list[float], provider: str, wf_type: str,
                         exclude_task: str) -> str | None:
    """Aynı workflow_type içinde near-dup memory'nin task_id'si (yoksa None)."""
    try:
        async with httpx.AsyncClient(base_url=settings.qdrant_url, timeout=10) as c:
            r = await c.post(f"/collections/{COLLECTION}/points/search", json={
                "vector": vector, "limit": 1, "with_payload": True,
                "filter": {"must": [{"key": "workflow_type", "match": {"value": wf_type}}]},
            })
            if r.status_code != 200:
                return None
            res = r.json().get("result", [])
    except Exception:  # noqa: BLE001
        return None
    if not res:
        return None
    top = res[0]
    tid = (top.get("payload") or {}).get("task_id")
    if top.get("score", 0) >= _dedup_threshold(provider) and tid and tid != exclude_task:
        return tid
    return None


async def _reinforce(s, task_id: str) -> None:
    """Var olan memory'yi güçlendir: retrieval++ , last_used=now, value recompute."""
    from sqlalchemy import select
    row = (await s.execute(select(MemoryEntry).where(MemoryEntry.task_id == task_id))).scalar_one_or_none()
    if not row:
        return
    row.retrieval_count = (row.retrieval_count or 0) + 1
    row.last_used_at = datetime.now(timezone.utc)
    row.value_score = compute_value(row.reuse_success_count, row.retrieval_count,
                                    row.created_at, row.refinement_summary)


async def consolidate(s) -> dict:
    """Periyodik konsolidasyon: value re-score (decay) + forgetting (prune Postgres+Qdrant)."""
    from sqlalchemy import select
    if not settings.memory_available:
        return {"rescored": 0, "evicted": 0}
    now = datetime.now(timezone.utc)
    rows = (await s.execute(select(MemoryEntry).where(MemoryEntry.status == "indexed"))).scalars().all()
    rescored = 0
    for r in rows:
        r.value_score = compute_value(r.reuse_success_count, r.retrieval_count,
                                      r.created_at, r.refinement_summary, now)
        rescored += 1

    # FORGETTING — evict adayları
    evict: set[str] = set()
    by_type: dict[str, list] = {}
    for r in rows:
        by_type.setdefault(r.workflow_type or "build", []).append(r)
    for entries in by_type.values():
        entries.sort(key=lambda x: -x.value_score)
        # per-type cap
        for r in entries[KEEP_PER_TYPE:]:
            evict.add(r.task_id)
        # düşük-değer + eski + hiç kullanılmamış
        for r in entries:
            age_days = (now - r.created_at).total_seconds() / 86400.0 if r.created_at else 0.0
            if age_days > MIN_AGE_DAYS and (r.reuse_success_count or 0) == 0 and r.value_score < FORGET_THRESHOLD:
                evict.add(r.task_id)
    # global cap — en düşük value'lardan
    if len(rows) - len(evict) > MAX_MEMORIES:
        survivors = sorted([r for r in rows if r.task_id not in evict], key=lambda x: x.value_score)
        for r in survivors[: (len(rows) - len(evict) - MAX_MEMORIES)]:
            evict.add(r.task_id)

    # uygula: Qdrant + Postgres sil
    for tid in evict:
        try:
            async with httpx.AsyncClient(base_url=settings.qdrant_url, timeout=10) as c:
                await c.post(f"/collections/{COLLECTION}/points/delete?wait=true",
                             json={"points": [_point_id(tid)]})
        except Exception:  # noqa: BLE001
            pass
    if evict:
        from sqlalchemy import delete
        await s.execute(delete(MemoryEntry).where(MemoryEntry.task_id.in_(evict)))
    print(f"[memory] consolidate: rescored={rescored} evicted={len(evict)}", flush=True)
    return {"rescored": rescored, "evicted": len(evict)}


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
    # v0.8.1 RE-RANK: value_score'u harmanla (final = α·similarity + β·value)
    from sqlalchemy import select
    tids = [h.get("task_id") for h in hits if h.get("task_id")]
    vmap: dict[str, float] = {}
    if tids:
        vrows = (await s.execute(
            select(MemoryEntry.task_id, MemoryEntry.value_score).where(MemoryEntry.task_id.in_(tids))
        )).all()
        vmap = {tid: (vs if vs is not None else 1.0) for tid, vs in vrows}
    for h in hits:
        h["value_score"] = vmap.get(h.get("task_id"), 1.0)
        h["final"] = round(RANK_ALPHA * h["score"] + RANK_BETA * h["value_score"], 4)
    # diversity: unique workflow_type first, sonra final skor
    seen_types: dict[str, int] = {}
    diverse: list[dict] = []
    for h in sorted(hits, key=lambda x: -x["final"]):
        t = h.get("workflow_type", "build")
        if seen_types.get(t, 0) >= MAX_PER_TAG:
            continue
        seen_types[t] = seen_types.get(t, 0) + 1
        diverse.append(h)
    diverse.sort(key=lambda x: (list(seen_types).index(x.get("workflow_type", "build")), -x["final"]))
    selected = diverse[:MAX_MEMORY_CONTEXT]

    avg = round(sum(h["score"] for h in selected) / len(selected), 4) if selected else 0.0
    confidence = "high" if avg >= 0.90 else "medium" if avg >= 0.85 else "low"
    # drift guard: top hit type, inferred ailesinde değilse bir kademe düş
    if selected and _family(selected[0].get("workflow_type")) != _family(inferred_type):
        confidence = {"high": "medium", "medium": "low", "low": "low"}[confidence]

    # retrieval_count++ + last_used_at (recall edilenler)
    if selected:
        await s.execute(
            update(MemoryEntry).where(MemoryEntry.task_id.in_([h["task_id"] for h in selected]))
            .values(retrieval_count=MemoryEntry.retrieval_count + 1,
                    last_used_at=datetime.now(timezone.utc))
        )
    return {"hits": selected, "avg_score": avg, "confidence": confidence}


async def mark_reuse_success(s, memory_ids: list[str]) -> None:
    if not memory_ids:
        return
    await s.execute(
        update(MemoryEntry).where(MemoryEntry.task_id.in_(memory_ids))
        .values(reuse_success_count=MemoryEntry.reuse_success_count + 1)
    )
