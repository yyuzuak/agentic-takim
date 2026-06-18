"""Event-sourced context reducer — SINGLE WRITER.

`reduce(events)` saf/deterministik: event log → snapshot. `apply(s, task_id)`
event log'u okur, snapshot + projeksiyonları (artifacts/critiques) yeniden kurar.
Orchestrator/agent ASLA snapshot yazmaz; yalnız buradan geçer.
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, select

from .models import TaskArtifact, TaskContextEvent, TaskContextSnapshot, TaskCritique


def reduce(events: list[dict]) -> dict:
    """Saf fonksiyon: aynı event listesi → aynı snapshot (replay garanti)."""
    snap: dict = {"goal": None, "shared": {"decisions": [], "artifacts": {}}, "agents": {}}
    for e in events:
        et, agent, node_key, payload = e["type"], e.get("agent"), e.get("node_key"), e.get("payload", {})
        if et == "task.init":
            snap["goal"] = payload.get("goal")
        elif et == "artifact.created":
            ns = snap["agents"].setdefault(agent or "?", {})
            ns.setdefault("artifacts", {})[node_key] = {"kind": payload.get("kind"), "content": payload.get("content")}
            snap["shared"]["artifacts"][node_key] = {"agent": agent, "kind": payload.get("kind")}
        elif et == "critique":
            ns = snap["agents"].setdefault(agent or "?", {})
            ns.setdefault("critiques", []).append({
                "target_node": payload.get("target_node"), "score": payload.get("score"),
                "issues": payload.get("issues", []), "suggestions": payload.get("suggestions", []),
            })
        elif et == "decision.made":
            snap["shared"]["decisions"].append({"agent": agent, "node_key": node_key, "decision": payload.get("decision")})
    return snap


async def _events(s, task_id: str) -> list[dict]:
    rows = (await s.execute(
        select(TaskContextEvent).where(TaskContextEvent.task_id == task_id).order_by(TaskContextEvent.seq)
    )).scalars().all()
    return [{"type": r.type, "agent": r.agent, "node_key": r.node_key, "payload": r.payload} for r in rows]


async def next_seq(s, task_id: str) -> int:
    rows = (await s.execute(select(TaskContextEvent.seq).where(TaskContextEvent.task_id == task_id))).scalars().all()
    return (max(rows) + 1) if rows else 0


async def apply(s, task_id: str) -> dict:
    """Event log'dan snapshot + projeksiyonları yeniden kur (tek yazıcı). version = event sayısı."""
    rows = (await s.execute(
        select(TaskContextEvent).where(TaskContextEvent.task_id == task_id).order_by(TaskContextEvent.seq)
    )).scalars().all()
    events = [{"type": r.type, "agent": r.agent, "node_key": r.node_key, "payload": r.payload} for r in rows]
    snap = reduce(events)
    version = len(events)

    # snapshot upsert
    existing = await s.get(TaskContextSnapshot, task_id)
    if existing is None:
        s.add(TaskContextSnapshot(task_id=task_id, snapshot=snap, version=version))
    else:
        existing.snapshot = snap
        existing.version = version

    # projeksiyonları yeniden kur (deterministik)
    await s.execute(delete(TaskArtifact).where(TaskArtifact.task_id == task_id))
    await s.execute(delete(TaskCritique).where(TaskCritique.task_id == task_id))
    for r in rows:
        if r.type == "artifact.created":
            s.add(TaskArtifact(id=str(uuid4()), task_id=task_id, node_key=r.node_key, agent=r.agent,
                               kind=r.payload.get("kind", "draft"), content=r.payload.get("content", {})))
        elif r.type == "critique":
            s.add(TaskCritique(id=str(uuid4()), task_id=task_id, target_node=r.payload.get("target_node"),
                               critic_agent=r.agent, score=r.payload.get("score"),
                               issues=r.payload.get("issues", []), suggestions=r.payload.get("suggestions", [])))
    return {"version": version, "snapshot": snap}
