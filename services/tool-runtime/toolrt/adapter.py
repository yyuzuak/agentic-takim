"""ToolAdapter Protocol — v1.1-a

Tüm adaptörler (Simulated, ERP, WhatsApp, …) bu contract'ı implement eder.
main.py'deki HANDLERS dict'i ADAPTER_REGISTRY ile replace edilir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class AdapterContext:
    exec_id: str
    task_id: str
    node_key: str
    dry_run: bool = False
    attempt: int = 0
    secrets: dict[str, str] = field(default_factory=dict)


@dataclass
class HealthResult:
    adapter: str
    status: str          # "healthy" | "degraded" | "down"
    latency_ms: int | None = None
    detail: str | None = None

    def dict(self) -> dict:
        return {"adapter": self.adapter, "status": self.status,
                "latency_ms": self.latency_ms, "detail": self.detail}


@runtime_checkable
class ToolAdapter(Protocol):
    """Her adaptörün uygulaması gereken arayüz."""
    name: str
    permission: str          # "read" | "write" | "external_send"

    async def execute(self, args: dict[str, Any], ctx: AdapterContext) -> dict[str, Any]:
        """Gerçek (veya simulated) yan etkiyi çalıştır."""
        ...

    async def compensate(self, args: dict[str, Any], exec_id: str) -> dict[str, Any]:
        """Daha önce execute edilmiş bir çağrıyı geri al."""
        ...

    async def healthcheck(self) -> HealthResult:
        """Adapter sağlık kontrolü (bağlantı, auth, latency)."""
        ...

    def capabilities(self) -> dict[str, bool]:
        """Adapter yetenekleri: dry_run, compensation, bulk, rate_limit."""
        ...

    def validate_args(self, args: dict[str, Any]) -> list[str]:
        """Argüman doğrulama — boş liste geçerli demek."""
        ...
