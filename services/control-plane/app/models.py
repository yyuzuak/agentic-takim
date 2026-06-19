from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
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
    # HITL (v0.5)
    require_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_plan_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_modified_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approval_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # v0.6 — düğüm payload'ına geçen ortak girdiler (fault injection + genel)
    inputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TaskPlanVersion(Base):
    """Plan'ın değişmez (immutable) sürüm geçmişi — audit zemini (v0.5.1)."""
    __tablename__ = "task_plan_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_json: Mapped[list] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeadLetterNode(Base):
    """Kalıcı başarısız düğüm — DLQ source of truth (audit + replay)."""
    __tablename__ = "dead_letter_nodes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    node_id: Mapped[str] = mapped_column(String, index=True)
    node_key: Mapped[str] = mapped_column(String, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_history: Mapped[list | None] = mapped_column(JSON, default=list)
    dag_context_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    dependency_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessedExecution(Base):
    """Fingerprint dedup — her node execution bir kez kesinleşir (exactly-once final state)."""
    __tablename__ = "processed_executions"

    exec_id: Mapped[str] = mapped_column(String, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------- v0.7 -------
class TaskContextEvent(Base):
    """Event-sourced context — değişmez truth (append-only). Snapshot bundan türetilir."""
    __tablename__ = "task_context_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # monotonic, task içi
    type: Mapped[str] = mapped_column(String, nullable=False)  # task.init|artifact.created|critique|decision.made
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    node_key: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    exec_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskContextSnapshot(Base):
    """Türetilmiş snapshot (materialized cache). TEK YAZAN = context_reducer."""
    __tablename__ = "task_context_snapshot"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TaskArtifact(Base):
    """Artifact projeksiyonu — producer/synthesizer çıktıları (provenance)."""
    __tablename__ = "task_artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    node_key: Mapped[str] = mapped_column(String, nullable=False)
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # draft | consensus | ...
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ToolInvocation(Base):
    """Tool çağrısı audit + idempotency. UNIQUE(exec_id) → at-most-once yan etki."""
    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    node_key: Mapped[str] = mapped_column(String, nullable=False)
    tool: Mapped[str] = mapped_column(String, nullable=False)
    args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    exec_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="requested")  # requested|success|failed
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rate_limited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schema_errors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolCompensation(Base):
    """Compensation kaydı — INV-1: yalnızca successful invocation sonrası.
    compensate_fn=NULL → geri alma imkânsız (örn. send_whatsapp)."""
    __tablename__ = "tool_compensations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    node_key: Mapped[str] = mapped_column(String, nullable=False)
    tool: Mapped[str] = mapped_column(String, nullable=False)
    exec_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    compensate_fn: Mapped[str | None] = mapped_column(String, nullable=True)
    compensate_args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryEntry(Base):
    """Memory-aware planning kaydı — Postgres=source of truth, Qdrant=retrieval index.
    Yalnız başarılı (done) görevler girer. UNIQUE(task_id) → idempotent store."""
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String, nullable=False, default="done")
    plan: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    memory_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    workflow_type: Mapped[str | None] = mapped_column(String, nullable=True)
    planner_source: Mapped[str | None] = mapped_column(String, nullable=True)
    success_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    refinement_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retrieval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reuse_success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # pending|indexed
    provider: Mapped[str | None] = mapped_column(String, nullable=True)  # local|openai
    parent_memory_ids: Mapped[list | None] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskCritique(Base):
    """Critique projeksiyonu — critic çıktısı (producer'ı DEĞİŞTİRMEZ)."""
    __tablename__ = "task_critiques"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    target_node: Mapped[str | None] = mapped_column(String, nullable=True)
    critic_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    issues: Mapped[list | None] = mapped_column(JSON, default=list)
    suggestions: Mapped[list | None] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    # v0.7 — execution semantics (business logic değil): producer | critic | synthesizer
    node_role: Mapped[str] = mapped_column(String, nullable=False, default="producer")
    msg_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # v0.6 — fault model / retry
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_policy: Mapped[str] = mapped_column(String, nullable=False, default="exponential")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    exec_id: Mapped[str | None] = mapped_column(String, nullable=True)
    retry_history: Mapped[list | None] = mapped_column(JSON, default=list)
    # v0.7.1 — refinement loop (forward expansion)
    refine_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refine_group: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # v0.9 — node kind (reasoning | tool | approval) + tool spec
    node_kind: Mapped[str] = mapped_column(String, nullable=False, default="reasoning")
    tool: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
