"""Simulated tool registry (v0.9) — gerçek dış çağrı YOK (sandbox stub).

Her tool deterministik sahte sonuç döner. Gerçek adaptörler (ERP/WhatsApp/CRM/SQL)
v0.9.1 Tool Safety Layer'da. İzin/permission tools.json'dan gelir.
"""
from __future__ import annotations

import json
import os
import time

_CATALOG_PATH = os.environ.get("TOOLS_CONFIG", "/app/config/tools.json")


def load_catalog() -> dict:
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    raw.pop("$comment", None)
    return raw


# --- simulated tool handlers (deterministik) ---
def _check_stock(args: dict) -> dict:
    sku = args.get("sku", "UNKNOWN")
    return {"sku": sku, "available": 42, "in_stock": True}


def _create_quote(args: dict) -> dict:
    return {"quote_id": f"Q-{abs(hash(json.dumps(args, sort_keys=True))) % 100000}",
            "customer": args.get("customer"), "items": args.get("items", [])}


def _generate_pdf(args: dict) -> dict:
    qid = args.get("quote_id", "Q-0")
    return {"pdf_url": f"file:///quotes/{qid}.pdf", "pages": 2}


def _send_whatsapp(args: dict) -> dict:
    # SİMÜLASYON — gerçek gönderim yok. Tek "gönderim" idempotency ile garanti.
    return {"to": args.get("to"), "doc": args.get("doc"), "delivered": True,
            "message_id": f"wamid-{int(time.time()*1000)%1000000}"}


HANDLERS = {
    "check_stock": _check_stock,
    "create_quote": _create_quote,
    "generate_pdf": _generate_pdf,
    "send_whatsapp": _send_whatsapp,
}
