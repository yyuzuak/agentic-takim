"""Agent Registry v1 — ARCHITECTURE.md Bölüm 5. config/agents.json bu şemaya uyar."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    ORCHESTRATOR = "orchestrator"
    AGENT = "agent"
    META = "meta"


class AgentDef(BaseModel):
    display_name: str
    role: str
    type: AgentType = AgentType.AGENT
    skills: list[str] = Field(default_factory=list)


class Registry(BaseModel):
    agents: dict[str, AgentDef]

    def skill_to_agent(self) -> dict[str, str]:
        """Routing için skill → agent eşlemesi (meta ajanlar hariç)."""
        mapping: dict[str, str] = {}
        for agent_id, agent in self.agents.items():
            if agent.type == AgentType.META:
                continue
            for skill in agent.skills:
                mapping.setdefault(skill, agent_id)
        return mapping
