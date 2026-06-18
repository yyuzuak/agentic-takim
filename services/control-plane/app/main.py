from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import bus, orchestrator
from .config import settings
from .db import get_session
from .models import (
    Agent,
    AgentSkill,
    DeadLetterNode,
    Task,
    TaskContextEvent,
    TaskContextSnapshot,
    TaskNode,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.nc = None
    app.state.js = None
    try:
        nc = await bus.connect()
        app.state.nc = nc
        app.state.js = nc.jetstream()
        app.state._consumer = asyncio.create_task(bus.result_consumer(app.state.js))
        app.state._scheduler = asyncio.create_task(orchestrator.retry_scheduler(app.state.js))
    except Exception as e:  # noqa: BLE001 — NATS yoksa /health yine ayakta kalmalı
        print(f"! NATS bağlantısı kurulamadı: {e}")
    yield
    for attr in ("_consumer", "_scheduler"):
        t = getattr(app.state, attr, None)
        if t:
            t.cancel()
    if app.state.nc:
        await app.state.nc.drain()


app = FastAPI(title="Agentic Takım — Control Plane", version="0.2.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "control-plane",
        "nats": app.state.js is not None,
        "features": {
            "llm": settings.llm_available,
            "memory": settings.memory_available,
            "observability": settings.observability_available,
        },
    }


@app.get("/agents")
async def list_agents(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(Agent))).scalars().all()
    agents = []
    for a in rows:
        skill_ids = (
            await session.execute(select(AgentSkill.skill_id).where(AgentSkill.agent_id == a.id))
        ).scalars().all()
        agents.append({"id": a.id, "display_name": a.display_name, "role": a.role, "type": a.type, "skills": skill_ids})
    return {"count": len(agents), "agents": agents}


# --------------------------------------------------------------- tasks ------
class TaskIn(BaseModel):
    goal: str
    skill: str | None = None       # verilirse tek düğüm; verilmezse Kaptan DAG'a böler
    type: str | None = None        # "build" | "research" (opsiyonel)
    require_approval: bool = False  # true → awaiting_approval (HITL)
    actor: str = "anonymous"
    inputs: dict = {}               # düğüm payload'ına geçer (fault injection vb.)
    retry_policy: str | None = None  # immediate | exponential | manual
    max_retries: int | None = None


class ActorIn(BaseModel):
    actor: str = "anonymous"


class RejectIn(BaseModel):
    actor: str = "anonymous"
    reason: str | None = None


class EditIn(BaseModel):
    actor: str = "anonymous"
    nodes: list[dict]


class ReplayIn(BaseModel):
    actor: str = "anonymous"
    reset_retries: bool = True


def _raise_for(result: dict) -> None:
    err = result.get("error")
    if err == "not_found":
        raise HTTPException(404, "görev bulunamadı")
    if err == "invalid_state":
        raise HTTPException(409, f"geçersiz durum geçişi (mevcut: {result.get('status')})")
    if err == "invalid_plan":
        raise HTTPException(422, f"geçersiz plan: {result.get('reason')}")


@app.post("/tasks", status_code=202)
async def create_task(body: TaskIn, request: Request) -> dict:
    """Kaptan: intent parsing + DAG decomposition. require_approval ise HITL kapısı."""
    js = request.app.state.js
    if js is None:
        raise HTTPException(503, "NATS bus hazır değil")
    return await orchestrator.start_workflow(
        js, body.goal, body.skill, body.type, body.require_approval, body.actor,
        body.inputs, body.retry_policy, body.max_retries,
    )


@app.get("/tasks/{task_id}/plan")
async def get_plan(task_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "görev bulunamadı")
    return {"task_id": task.id, "version": task.current_plan_version, "plan": task.plan}


@app.get("/tasks/{task_id}/approval")
async def get_approval(task_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "görev bulunamadı")
    return {
        "task_id": task.id,
        "status": task.status,
        "version": task.current_plan_version,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "last_modified_by": task.last_modified_by,
        "approval_deadline": task.approval_deadline.isoformat() if task.approval_deadline else None,
    }


@app.post("/tasks/{task_id}/approve")
async def approve_task(task_id: str, body: ActorIn, request: Request) -> dict:
    result = await orchestrator.approve(request.app.state.js, task_id, body.actor)
    _raise_for(result)
    return result


@app.post("/tasks/{task_id}/reject")
async def reject_task(task_id: str, body: RejectIn, request: Request) -> dict:
    result = await orchestrator.reject(request.app.state.js, task_id, body.actor, body.reason)
    _raise_for(result)
    return result


@app.post("/tasks/{task_id}/edit")
async def edit_task(task_id: str, body: EditIn, request: Request) -> dict:
    result = await orchestrator.edit(request.app.state.js, task_id, body.actor, body.nodes)
    _raise_for(result)
    return result


@app.get("/tasks/{task_id}")
async def get_task(task_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "görev bulunamadı")
    nodes = (await session.execute(select(TaskNode).where(TaskNode.task_id == task_id))).scalars().all()
    return {
        "id": task.id,
        "goal": task.goal,
        "status": task.status,
        "result": task.result,
        "error": task.error,
        "nodes": [
            {"key": n.node_key, "agent": n.agent, "skill": n.skill, "role": n.node_role, "depends_on": n.depends_on,
             "status": n.status, "result": n.result, "retry_count": n.retry_count,
             "max_retries": n.max_retries, "retry_policy": n.retry_policy, "error_code": n.error_code,
             "retry_at": n.retry_at.isoformat() if n.retry_at else None}
            for n in sorted(nodes, key=lambda x: x.node_key)
        ],
    }


@app.get("/tasks/{task_id}/dlq")
async def get_dlq(task_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(DeadLetterNode).where(DeadLetterNode.task_id == task_id))).scalars().all()
    return {"count": len(rows), "dead_letter_nodes": [
        {"node_id": r.node_id, "node_key": r.node_key, "error_code": r.error_code,
         "retry_count": r.retry_count, "last_error": r.last_error, "retry_history": r.retry_history}
        for r in rows
    ]}


@app.post("/tasks/{task_id}/nodes/{node_key}/retry")
async def retry_node(task_id: str, node_key: str, body: ActorIn, request: Request) -> dict:
    result = await orchestrator.manual_retry(request.app.state.js, task_id, node_key, body.actor)
    _raise_for(result)
    return result


@app.post("/dlq/{node_id}/replay")
async def replay_dlq(node_id: str, body: ReplayIn, request: Request) -> dict:
    result = await orchestrator.dlq_replay(request.app.state.js, node_id, body.actor, body.reset_retries)
    _raise_for(result)
    return result


@app.get("/tasks/{task_id}/context")
async def get_context(task_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    snap = await session.get(TaskContextSnapshot, task_id)
    if snap is None:
        raise HTTPException(404, "context bulunamadı")
    return {"task_id": task_id, "version": snap.version, "snapshot": snap.snapshot}


@app.get("/tasks/{task_id}/events")
async def get_events(task_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(
        select(TaskContextEvent).where(TaskContextEvent.task_id == task_id).order_by(TaskContextEvent.seq)
    )).scalars().all()
    return {"count": len(rows), "events": [
        {"seq": r.seq, "type": r.type, "agent": r.agent, "node_key": r.node_key, "payload": r.payload}
        for r in rows
    ]}


@app.get("/metrics")
async def metrics() -> dict:
    """Retry/DLQ orkestrasyon sayaçları (hybrid event+DB debugging)."""
    return dict(orchestrator._metrics)


@app.get("/")
async def root() -> dict:
    return {"name": "Agentic Takım", "docs": "/docs", "health": "/health", "agents": "/agents", "tasks": "POST /tasks"}
