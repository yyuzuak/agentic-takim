"""SimulatedAdapter — v1.1-a

Mevcut tools.py handler'larını ToolAdapter Protocol'üne taşır.
Backward compat: v0.9/v0.9.1 testleri bozulmaz. dry_run her zaman desteklenir.
"""
from __future__ import annotations

import json
import time

from ..adapter import AdapterContext, HealthResult, ToolAdapter


class _SimulatedBase:
    permission: str = "read"
    supports_dry_run: bool = True
    supports_compensation: bool = False

    def capabilities(self) -> dict:
        return {"dry_run": True, "compensation": self.supports_compensation,
                "bulk": False, "rate_limit": True, "circuit_breaker": False}

    def validate_args(self, args: dict) -> list[str]:
        return []

    async def compensate(self, args: dict, exec_id: str) -> dict:
        return {"reversible": False, "note": "simulated — no real side effect"}

    async def healthcheck(self) -> HealthResult:
        return HealthResult(adapter=self.name, status="healthy", latency_ms=0,
                            detail="simulated — always healthy")


class CheckStockAdapter(_SimulatedBase):
    name = "check_stock"
    permission = "read"

    async def execute(self, args: dict, ctx: AdapterContext) -> dict:
        sku = args.get("sku", "UNKNOWN")
        return {"sku": sku, "available": 42, "in_stock": True}


class CreateQuoteAdapter(_SimulatedBase):
    name = "create_quote"
    permission = "write"
    supports_compensation = True

    async def execute(self, args: dict, ctx: AdapterContext) -> dict:
        return {"quote_id": f"Q-{abs(hash(json.dumps(args, sort_keys=True))) % 100000}",
                "customer": args.get("customer"), "items": args.get("items", [])}

    async def compensate(self, args: dict, exec_id: str) -> dict:
        quote_id = args.get("quote_id") or f"Q-{abs(hash(json.dumps(args, sort_keys=True))) % 100000}"
        return {"reversible": True, "cancelled_quote_id": quote_id, "exec_id": exec_id}


class GeneratePDFAdapter(_SimulatedBase):
    name = "generate_pdf"
    permission = "write"

    async def execute(self, args: dict, ctx: AdapterContext) -> dict:
        qid = args.get("quote_id", "Q-0")
        return {"pdf_url": f"file:///quotes/{qid}.pdf", "pages": 2}


class SendWhatsAppSimulatedAdapter(_SimulatedBase):
    name = "send_whatsapp"
    permission = "external_send"

    async def execute(self, args: dict, ctx: AdapterContext) -> dict:
        return {"to": args.get("to"), "doc": args.get("doc"), "delivered": True,
                "message_id": f"wamid-{int(time.time()*1000)%1000000}", "_simulated": True}


# Registry builder — catalog'dan çağrılır
SIMULATED_ADAPTERS: dict[str, ToolAdapter] = {
    "check_stock":   CheckStockAdapter(),
    "create_quote":  CreateQuoteAdapter(),
    "generate_pdf":  GeneratePDFAdapter(),
    "send_whatsapp": SendWhatsAppSimulatedAdapter(),
}
