from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="agent")

    skills: Mapped[list["AgentSkill"]] = relationship(back_populates="agent", cascade="all, delete-orphan")


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String, primary_key=True)


class AgentSkill(Base):
    __tablename__ = "agent_skills"

    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)

    agent: Mapped["Agent"] = relationship(back_populates="skills")


class Task(Base):
    """ACP görevi — yaşam döngüsü: pending → running → done | failed (CLAUDE.md Bölüm 9)."""
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String, index=True)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    skill: Mapped[str | None] = mapped_column(String, nullable=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    plan: Mapped[list | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TaskNode(Base):
    """DAG düğümü — bir alt görev. depends_on, aynı task içindeki node_key'lere referans."""
    __tablename__ = "task_nodes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    node_key: Mapped[str] = mapped_column(String, nullable=False)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    skill: Mapped[str | None] = mapped_column(String, nullable=True)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    msg_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
