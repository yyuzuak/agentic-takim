"""ERPAdapter — v1.1-b

Provider-agnostic ERP adapter. Desteklenen: BizimHesap, Logo, Netsis, Mikro.
dry_run=True → API çağrısı yok, deterministik sahte veri.
Failure model: HTTP status → ErrorCode (yeniden kullanılabilir helper).
"""
from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any

import httpx

from ..adapter import AdapterContext, HealthResult


class ERPProvider(str, Enum):
    BIZIMHESAP = "bizimhesap"
    LOGO = "logo"
    NETSIS = "netsis"
    MIKRO = "mikro"


# Provider → endpoint prefix mapping
_PREFIX: dict[ERPProvider, str] = {
    ERPProvider.BIZIMHESAP: "/api/v1",
    ERPProvider.LOGO:       "/rest/v1",
    ERPProvider.NETSIS:     "/netsis/api",
    ERPProvider.MIKRO:      "/mikro/api/v1",
}


def _http_error_code(status: int) -> str:
    if status in (401, 403):
        return "PERMISSION"
    if status in (400, 404, 422):
        return "SCHEMA"
    if status == 429:
        return "RATE_LIMIT"
    if status >= 500:
        return "TRANSIENT"
    return "UNKNOWN"


class ERPError(Exception):
    def __init__(self, code: str, message: str, http_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class ERPAdapter:
    permission = "write"
    supports_compensation = True

    def __init__(self, provider: ERPProvider, base_url: str, api_key: str, tool_name: str):
        self.name = tool_name
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._prefix = _PREFIX.get(provider, "/api/v1")

    def _url(self, path: str) -> str:
        return f"{self.base_url}{self._prefix}{path}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def capabilities(self) -> dict:
        return {"dry_run": True, "compensation": True, "bulk": False,
                "rate_limit": True, "circuit_breaker": True}

    def validate_args(self, args: dict[str, Any]) -> list[str]:
        return []

    async def healthcheck(self) -> HealthResult:
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(self._url("/health"), headers=self._headers())
            latency = int((time.monotonic() - t0) * 1000)
            if r.status_code < 300:
                return HealthResult(adapter=self.name, status="healthy", latency_ms=latency)
            if r.status_code < 500:
                return HealthResult(adapter=self.name, status="degraded", latency_ms=latency,
                                    detail=f"HTTP {r.status_code}")
            return HealthResult(adapter=self.name, status="down", latency_ms=latency,
                                detail=f"HTTP {r.status_code}")
        except Exception as e:
            latency = int((time.monotonic() - t0) * 1000)
            return HealthResult(adapter=self.name, status="down", latency_ms=latency, detail=str(e))

    async def execute(self, args: dict[str, Any], ctx: AdapterContext) -> dict[str, Any]:
        if ctx.dry_run:
            return self._simulate(args)

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                result, http_status = await self._dispatch(client, args)
            except httpx.TimeoutException:
                raise ERPError("TIMEOUT", "ERP request timeout")

        return result

    def _simulate(self, args: dict) -> dict:
        """Deterministik sahte veri — dry_run modunda API çağrısı yok."""
        if self.name == "check_stock":
            return {"sku": args.get("sku", "UNKNOWN"), "available": 42, "in_stock": True, "_simulated": True}
        if self.name == "create_quote":
            import json
            return {"quote_id": f"Q-{abs(hash(json.dumps(args, sort_keys=True))) % 100000}",
                    "customer": args.get("customer"), "items": args.get("items", []), "_simulated": True}
        if self.name == "generate_pdf":
            return {"pdf_url": f"file:///quotes/{args.get('quote_id', 'Q-0')}.pdf",
                    "pages": 2, "_simulated": True}
        return {"_simulated": True}

    async def _dispatch(self, client: httpx.AsyncClient, args: dict) -> tuple[dict, int]:
        if self.name == "check_stock":
            sku = args.get("sku", "")
            r = await client.get(self._url(f"/stock/{sku}"), headers=self._headers())
            if r.status_code >= 400:
                raise ERPError(_http_error_code(r.status_code),
                                f"ERP check_stock failed: {r.status_code}", r.status_code)
            return r.json(), r.status_code

        if self.name == "create_quote":
            r = await client.post(self._url("/quotes"), json=args, headers=self._headers())
            if r.status_code >= 400:
                raise ERPError(_http_error_code(r.status_code),
                                f"ERP create_quote failed: {r.status_code}", r.status_code)
            return r.json(), r.status_code

        if self.name == "generate_pdf":
            qid = args.get("quote_id", "")
            r = await client.get(self._url(f"/quotes/{qid}/pdf"), headers=self._headers())
            if r.status_code >= 400:
                raise ERPError(_http_error_code(r.status_code),
                                f"ERP generate_pdf failed: {r.status_code}", r.status_code)
            return {"pdf_url": r.headers.get("Location", f"{self.base_url}/quotes/{qid}.pdf"),
                    "pages": 2}, r.status_code

        raise ERPError("SCHEMA", f"Unknown ERP tool: {self.name}")

    async def compensate(self, args: dict[str, Any], exec_id: str) -> dict[str, Any]:
        """create_quote compensation: ERP'de quote'u iptal et."""
        if self.name != "create_quote":
            return {"reversible": False, "note": f"{self.name} is not reversible"}

        quote_id = args.get("quote_id")
        if not quote_id:
            import json
            quote_id = f"Q-{abs(hash(json.dumps(args, sort_keys=True))) % 100000}"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.delete(self._url(f"/quotes/{quote_id}"), headers=self._headers())
            if r.status_code >= 400 and r.status_code != 404:
                return {"reversible": False, "error": f"DELETE failed: {r.status_code}",
                        "exec_id": exec_id}
            return {"reversible": True, "cancelled_quote_id": quote_id, "exec_id": exec_id}
        except Exception as e:
            return {"reversible": False, "error": str(e), "exec_id": exec_id}
