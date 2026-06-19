"""WhatsAppAdapter — v1.1-c

WhatsApp Business Cloud API (graph.facebook.com/v19.0).
dry_run=True → API çağrısı yok, simulated message_id.
compensate() → geri alınamaz (non-reversible).
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from ..adapter import AdapterContext, HealthResult


class WhatsAppAdapter:
    name = "send_whatsapp"
    permission = "external_send"

    def __init__(self, token: str, phone_number_id: str):
        self.token = token
        self.phone_number_id = phone_number_id
        self._base = f"https://graph.facebook.com/v19.0/{phone_number_id}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def capabilities(self) -> dict:
        return {"dry_run": True, "compensation": False, "bulk": False,
                "rate_limit": True, "circuit_breaker": True}

    def validate_args(self, args: dict[str, Any]) -> list[str]:
        errors = []
        if not args.get("to"):
            errors.append("'to' alanı zorunlu")
        return errors

    async def healthcheck(self) -> HealthResult:
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"https://graph.facebook.com/v19.0/{self.phone_number_id}",
                    headers=self._headers(),
                    params={"fields": "display_phone_number"},
                )
            latency = int((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                return HealthResult(adapter=self.name, status="healthy", latency_ms=latency)
            return HealthResult(adapter=self.name, status="degraded", latency_ms=latency,
                                detail=f"HTTP {r.status_code}")
        except Exception as e:
            latency = int((time.monotonic() - t0) * 1000)
            return HealthResult(adapter=self.name, status="down", latency_ms=latency, detail=str(e))

    async def execute(self, args: dict[str, Any], ctx: AdapterContext) -> dict[str, Any]:
        if ctx.dry_run:
            return {"to": args.get("to"), "doc": args.get("doc"), "delivered": True,
                    "message_id": f"wamid-dry-{int(time.time()*1000)%1000000}", "_simulated": True}

        to = args.get("to", "")
        text = args.get("doc", "")

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                r = await client.post(f"{self._base}/messages", json=payload, headers=self._headers())
            except httpx.TimeoutException:
                from ..adapters.erp import ERPError
                raise ERPError("TIMEOUT", "WhatsApp API timeout")

        if r.status_code >= 400:
            from ..adapters.erp import ERPError, _http_error_code
            raise ERPError(_http_error_code(r.status_code),
                           f"WhatsApp send failed: {r.status_code}", r.status_code)

        data = r.json()
        messages = data.get("messages", [{}])
        return {
            "to": to,
            "delivered": True,
            "message_id": messages[0].get("id", ""),
        }

    async def compensate(self, args: dict[str, Any], exec_id: str) -> dict[str, Any]:
        return {"reversible": False, "note": "WhatsApp messages cannot be unsent", "exec_id": exec_id}
