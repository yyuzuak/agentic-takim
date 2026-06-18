"""Registry seed — config/agents.json → agents/skills/agent_skills tabloları.

agents.json kaynak; DB çalışma-zamanı (ileride UI'dan düzenlenebilir).
Idempotent: tekrar çalıştırılabilir (upsert mantığı).
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import delete

from agentic_schemas.agent_registry.v1 import Registry

from .config import settings
from .db import SessionLocal, engine
from .models import Agent, AgentSkill, Skill


async def seed() -> None:
    with open(settings.config_path, encoding="utf-8") as f:
        raw = json.load(f)
    raw.pop("$comment", None)
    registry = Registry.model_validate(raw)

    async with SessionLocal() as s:
        # Temiz yeniden seed (idempotent)
        await s.execute(delete(AgentSkill))
        await s.execute(delete(Agent))
        await s.execute(delete(Skill))

        all_skills: set[str] = set()
        for agent_id, agent in registry.agents.items():
            s.add(Agent(id=agent_id, display_name=agent.display_name, role=agent.role, type=agent.type.value))
            all_skills.update(agent.skills)
        for skill_id in sorted(all_skills):
            s.add(Skill(id=skill_id))
        await s.flush()

        for agent_id, agent in registry.agents.items():
            for skill_id in agent.skills:
                s.add(AgentSkill(agent_id=agent_id, skill_id=skill_id))

        await s.commit()

    print(f"✓ Seed tamam: {len(registry.agents)} ajan, {len(all_skills)} skill yüklendi.")

    if settings.memory_available:
        await _seed_example_memory()

    await engine.dispose()


async def _seed_example_memory() -> None:
    """memory profili açıksa Qdrant'a örnek bir hafıza kaydı yazar (kanıt)."""
    try:
        import httpx

        collection = "agent_memory"
        # Basit deterministik sahte vektör (gerçek embedding gerektirmez — kurulum kanıtı).
        vector = [0.01] * 1536
        point = {
            "points": [
                {
                    "id": 1,
                    "vector": vector,
                    "payload": {"type": "agent_memory", "agent": "kaptan", "content": "Örnek hafıza kaydı (seed)."},
                }
            ]
        }
        async with httpx.AsyncClient(base_url=settings.qdrant_url, timeout=10) as c:
            r = await c.put(f"/collections/{collection}/points?wait=true", json=point)
            r.raise_for_status()
        print("✓ Qdrant örnek hafıza kaydı yazıldı.")
    except Exception as e:  # noqa: BLE001 — seed best-effort
        print(f"! Qdrant örnek hafıza yazılamadı (atlanıyor): {e}")


if __name__ == "__main__":
    asyncio.run(seed())
