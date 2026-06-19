"""ACP v1 — Base Envelope ve ortak tipler. Kaynak: ACP.md Bölüm 1."""
from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

PROTOCOL_VERSION = "1.0"
SCHEMA_VERSION = "1"


class MessageType(str, Enum):
    TASK = "task"
    RESULT = "result"
    HANDOFF = "handoff"
    ERROR = "error"
    SYNC = "sync"
    ACK = "ack"
    CANCEL = "cancel"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESPONSE = "approval_response"


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Trust(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class ErrorCode(str, Enum):
    """ACP.md Bölüm 8 — hata taksonomisi."""
    TRANSIENT = "TRANSIENT"
    SCHEMA = "SCHEMA"
    LOGICAL = "LOGICAL"
    PERMISSION = "PERMISSION"
    BUDGET = "BUDGET"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"     # retryable; retry_after payload'da (v0.9.1)
    CIRCUIT_OPEN = "CIRCUIT_OPEN" # non-retryable; adapter devre dışı (v1.1-c)
    UNKNOWN = "UNKNOWN"


class Context(BaseModel):
    compressed_state: str | None = None
    global_constraints: list[str] = Field(default_factory=list)
    agent_memory_ref: str | None = None


class Envelope(BaseModel):
    """ACP Base Envelope — her ajanın gördüğü tek yapı (izolasyon).

    Tipli mesajlar için `messages.py` içindeki alt sınıfları kullanın
    (TaskMessage, ResultMessage, ...). Bu base, gevşek/generic senaryolar
    için `payload: dict` ile esnek kalır.
    """
    protocol_version: str = PROTOCOL_VERSION
    schema_version: str = SCHEMA_VERSION

    message_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    parent_id: UUID | None = None
    in_reply_to: UUID | None = None

    from_agent: str = Field(alias="from")
    to_agent: str = Field(alias="to")

    type: MessageType
    skill: str | None = None

    timestamp: int
    priority: Priority = Priority.NORMAL
    trust: Trust = Trust.TRUSTED

    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: list[str] = Field(default_factory=list)
    context: Context = Field(default_factory=Context)

    expected_output_schema: str | None = None
    ttl_ms: int = 300_000
    exec_timeout_ms: int = 120_000

    model_config = {"populate_by_name": True}
