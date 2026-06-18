from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .models import Agent, AgentSkill

app = FastAPI(title="Agentic Takım — Control Plane", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    """Migration'dan ÖNCE de 200 dönmeli (compose healthcheck bunu bekler).
    Bu yüzden DB tablolarına bağlı değildir."""
    return {
        "status": "ok",
        "service": "control-plane",
        "features": {
            "llm": settings.llm_available,
            "memory": settings.memory_available,
            "observability": settings.observability_available,
        },
    }


@app.get("/agents")
async def list_agents(session: AsyncSession = Depends(get_session)) -> dict:
    """Registry'den ajanları ve skill'lerini döner (seed sonrası dolu)."""
    rows = (await session.execute(select(Agent))).scalars().all()
    agents = []
    for a in rows:
        skill_ids = (
            await session.execute(select(AgentSkill.skill_id).where(AgentSkill.agent_id == a.id))
        ).scalars().all()
        agents.append(
            {"id": a.id, "display_name": a.display_name, "role": a.role, "type": a.type, "skills": skill_ids}
        )
    return {"count": len(agents), "agents": agents}


@app.get("/")
async def root() -> dict:
    return {"name": "Agentic Takım", "docs": "/docs", "health": "/health", "agents": "/agents"}
