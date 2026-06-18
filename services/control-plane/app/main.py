from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_schemas.acp.v1 import TaskMessage, TaskPayload
from agentic_schemas.events.v1 import Subject

from . import bus
from .config import settings
from .db import get_session
from .models import Agent, AgentSkill, Task
from .routing import route


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
    skill: str | None = None


@app.post("/tasks", status_code=202)
async def create_task(body: TaskIn, request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    """Kaptan: skill→agent route + ACP.TASK.CREATED yayını. trace_id = task id."""
    js = request.app.state.js
    if js is None:
        raise HTTPException(503, "NATS bus hazır değil")

    task_id = str(uuid4())
    agent = route(body.skill)

    task = Task(id=task_id, trace_id=task_id, agent=agent, skill=body.skill, goal=body.goal, status="pending")
    session.add(task)
    await session.commit()

    msg = TaskMessage(
        from_agent="kaptan",
        to_agent=agent,
        trace_id=UUID(task_id),
        skill=body.skill,
        timestamp=int(time.time()),
        payload=TaskPayload(goal=body.goal),
    )
    await js.publish(Subject.TASK_CREATED.value, msg.model_dump_json(by_alias=True).encode())

    task.status = "running"
    await session.commit()
    return {"task_id": task_id, "agent": agent, "skill": body.skill, "status": "running"}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "görev bulunamadı")
    return {
        "id": task.id,
        "agent": task.agent,
        "skill": task.skill,
        "goal": task.goal,
        "status": task.status,
        "result": task.result,
        "error": task.error,
    }


@app.get("/")
async def root() -> dict:
    return {"name": "Agentic Takım", "docs": "/docs", "health": "/health", "agents": "/agents", "tasks": "POST /tasks"}
