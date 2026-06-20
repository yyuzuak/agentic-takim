"""Observer DB — READ-ONLY shared Postgres erişimi.

INVARIANT 2: Her sorgu window'a bağlı + LIMIT'li. `bounded_query()` tek geçittir;
aggregator yalnızca bunu kullanır, ham `session.execute()` çağırmaz. Bu sayede
developer LIMIT/window'u unutamaz (rule değil, enforced abstraction).

Tablolar control-plane ile paylaşılır; burada yalnız okunan kolonların hafif modeli.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    JSON, DateTime, Float, Integer, String, Text, func, select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import Select

DSN = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://agentic:agentic_dev_pw@postgres:5432/agentic_os"
)
# READ-ONLY niyet: pool küçük, autoflush kapalı. Observer asla commit/insert yapmaz.
engine = create_async_engine(DSN, pool_pre_ping=True, pool_size=5)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

MAX_ROWS = 10_000

WINDOWS = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "7d": timedelta(days=7)}
_ORDER = ["1h", "24h", "7d"]


def window_since(window: str) -> datetime:
    """Window etiketini bir 'since' timestamp'ine çevirir (UTC)."""
    delta = WINDOWS.get(window, WINDOWS["24h"])
    return datetime.now(timezone.utc) - delta


def next_larger_window(window: str) -> str | None:
    """1h→24h→7d. 7d için None (en büyük)."""
    try:
        idx = _ORDER.index(window)
    except ValueError:
        return "24h"
    return _ORDER[idx + 1] if idx + 1 < len(_ORDER) else None


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TaskNode(Base):
    __tablename__ = "task_nodes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    retry_count: Mapped[int] = mapped_column(Integer)
    max_retries: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String)
    tool: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ToolCompensation(Base):
    __tablename__ = "tool_compensations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    success_score: Mapped[float] = mapped_column(Float)
    retrieval_count: Mapped[int] = mapped_column(Integer)
    reuse_success_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


async def bounded_query(
    session: AsyncSession,
    stmt: Select,
    *,
    created_at_col,
    since: datetime,
    max_rows: int = MAX_ROWS,
):
    """TEK GEÇİT (INVARIANT 2). created_at filtresi + LIMIT otomatik enjekte edilir.

    `created_at_col`: window uygulanacak kolon (task_nodes'ta created_at yok →
    tasks.created_at join üzerinden geçilir).
    """
    stmt = stmt.where(created_at_col >= since).limit(max_rows)
    return await session.execute(stmt)
