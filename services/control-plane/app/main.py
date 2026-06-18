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
from .models import Agent, AgentSkill, Task, TaskNode


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.nc = None
    app.state.js = None
    try:
        nc = await bus.connect()
        app.state.nc = nc
        app.state.js = nc.jetstream()
        app.state._consumer = asyncio.create_task(bus.result_consumer(app.state.js))
    except Exception as e:  # noqa: BLE001 — NATS yoksa /health yine ayakta kalmalı
        print(f"! NATS bağlantısı kurulamadı: {e}")
    yield
    task = getattr(app.state, "_consumer", None)
    if task:
        task.cancel()
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


class ActorIn(BaseModel):
    actor: str = "anonymous"


class RejectIn(BaseModel):
    actor: str = "anonymous"
    reason: str | None = None


class EditIn(BaseModel):
    actor: str = "anonymous"
    nodes: list[dict]


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
    return await orchestrator.start_workflow(js, body.goal, body.skill, body.type, body.require_approval, body.actor)


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
            {"key": n.node_key, "agent": n.agent, "skill": n.skill, "depends_on": n.depends_on,
             "status": n.status, "result": n.result}
            for n in sorted(nodes, key=lambda x: x.node_key)
        ],
    }


@app.get("/")
async def root() -> dict:
    return {"name": "Agentic Takım", "docs": "/docs", "health": "/health", "agents": "/agents", "tasks": "POST /tasks"}
