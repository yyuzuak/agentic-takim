"""tool-runtime DB — shared Postgres'teki tool_invocations tablosu (idempotency/audit).
Control-plane ile aynı tablo; burada hafif bir model tanımı."""
from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DSN = os.environ.get("DATABASE_URL", "postgresql+asyncpg://agentic:agentic_dev_pw@postgres:5432/agentic_os")
engine = create_async_engine(DSN, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String)
    node_key: Mapped[str] = mapped_column(String)
    tool: Mapped[str] = mapped_column(String)
    args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    exec_id: Mapped[str] = mapped_column(String, unique=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="requested")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
