"""Builder DB — shared Postgres'teki builds tablosu (control-plane 0012_builds sahibi)."""
from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DSN = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://agentic:agentic_dev_pw@postgres:5432/agentic_os"
)
engine = create_async_engine(DSN, pool_pre_ping=True, pool_size=5)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Build(Base):
    __tablename__ = "builds"

    build_id: Mapped[str] = mapped_column(String, primary_key=True)
    build_fingerprint: Mapped[str] = mapped_column(String, index=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    build_number: Mapped[int] = mapped_column(Integer, default=1)
    stack: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # validated | failed
    dag_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assembler_version: Mapped[str] = mapped_column(String)
    validator_version: Mapped[str] = mapped_column(String)
    validator_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    workspace_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def as_dict(self) -> dict:
        return {
            "build_id": self.build_id,
            "build_fingerprint": self.build_fingerprint,
            "task_id": self.task_id,
            "build_number": self.build_number,
            "stack": self.stack,
            "status": self.status,
            "dag_snapshot": self.dag_snapshot,
            "assembler_version": self.assembler_version,
            "validator_version": self.validator_version,
            "validator_result": self.validator_result,
            "file_count": self.file_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
