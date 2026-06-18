"""ACP v1 — Tipli mesaj modelleri. Kaynak: ACP.md Bölüm 2.

Her mesaj `Envelope`'ı genişletir; `type` sabittir ve `payload` ilgili tipli
modeldir. Böylece tek bir dict karmaşası yerine net, doğrulanabilir sözleşmeler olur.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .envelope import Envelope, ErrorCode, MessageType


# --------------------------------------------------------------- payloads ---
class TaskPayload(BaseModel):
    goal: str
    inputs: dict = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)


class ResultPayload(BaseModel):
    result: dict = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class HandoffPayload(BaseModel):
    reason: str
    context_summary: str | None = None
    open_questions: list[str] = Field(default_factory=list)


class CancelPayload(BaseModel):
    # budget_exceeded | user_abort | superseded
    reason: str


class ApprovalRequestPayload(BaseModel):
    action: str
    impact: str = "reversible"  # reversible | irreversible
    details: dict = Field(default_factory=dict)


class ApprovalResponsePayload(BaseModel):
    approved: bool


# --------------------------------------------------------------- messages ---
class TaskMessage(Envelope):
    type: MessageType = MessageType.TASK
    payload: TaskPayload


class ResultMessage(Envelope):
    type: MessageType = MessageType.RESULT
    payload: ResultPayload


class HandoffMessage(Envelope):
    type: MessageType = MessageType.HANDOFF
    payload: HandoffPayload


class ErrorMessage(Envelope):
    type: MessageType = MessageType.ERROR
    error_code: ErrorCode
    message: str


class AckMessage(Envelope):
    type: MessageType = MessageType.ACK
    status: str = "received"


class SyncMessage(Envelope):
    type: MessageType = MessageType.SYNC


class CancelMessage(Envelope):
    type: MessageType = MessageType.CANCEL
    payload: CancelPayload


class ApprovalRequestMessage(Envelope):
    type: MessageType = MessageType.APPROVAL_REQUEST
    payload: ApprovalRequestPayload


class ApprovalResponseMessage(Envelope):
    type: MessageType = MessageType.APPROVAL_RESPONSE
    payload: ApprovalResponsePayload
