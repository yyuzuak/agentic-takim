"""Events v1 — ACP.md Bölüm 6. Kanonik JetStream subject'leri TEK kaynaktan."""
from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Subject(str, Enum):
    """init-nats.sh bu subject'lerle stream oluşturur. İsimler sabittir."""
    TASK_CREATED = "ACP.TASK.CREATED"
    TASK_COMPLETED = "ACP.TASK.COMPLETED"
    TASK_FAILED = "ACP.TASK.FAILED"
    TASK_DLQ = "ACP.TASK.DLQ"
    HANDOFF_REQUESTED = "ACP.HANDOFF.REQUESTED"
    AGENT_HEARTBEAT = "ACP.AGENT.HEARTBEAT"
    SYSTEM_EVENT = "ACP.SYSTEM.EVENT"


# init-nats.sh ile birebir tutarlı olmalı.
ALL_SUBJECTS: list[str] = [s.value for s in Subject]


class Event(BaseModel):
    subject: Subject
    trace_id: UUID
    from_agent: str = Field(alias="from")
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}
