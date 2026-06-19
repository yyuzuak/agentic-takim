"""Tool catalog + ADAPTER_REGISTRY builder — v1.1-a

load_catalog() JSON okur.
build_registry() her tool için adapter_class'a göre ToolAdapter döndürür.
Bilinmeyen / secrets eksik → SimulatedAdapter fallback (graceful degradation).
"""
from __future__ import annotations

import json
import os

from .adapter import ToolAdapter
from .adapters.simulated import SIMULATED_ADAPTERS

_CATALOG_PATH = os.environ.get("TOOLS_CONFIG", "/app/config/tools.json")


def load_catalog() -> dict:
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    raw.pop("$comment", None)
    return raw


def build_registry(catalog: dict) -> dict[str, ToolAdapter]:
    """
    catalog["tools"] içindeki her entry için adapter seç:
    1. adapter_class belirtilmişse o sınıfı yükle (lazy import)
    2. Secrets eksikse SimulatedAdapter'a fallback
    3. Bilinmiyorsa SimulatedAdapter (varsa) veya skip
    """
    from . import secrets as sec

    registry: dict[str, ToolAdapter] = {}
    tools = catalog.get("tools") or {}

    for tool_name, spec in tools.items():
        adapter_class = spec.get("adapter_class", "SimulatedAdapter")

        if adapter_class == "ERPAdapter":
            if sec.resolver.available("erp"):
                try:
                    from .adapters.erp import ERPAdapter, ERPProvider
                    provider_str = sec.resolver.inject("erp").get("provider", "bizimhesap")
                    provider = ERPProvider(provider_str) if provider_str in ERPProvider._value2member_map_ else ERPProvider.BIZIMHESAP
                    base_url = sec.resolver.inject("erp")["base_url"]
                    api_key = sec.resolver.inject("erp")["api_key"]
                    registry[tool_name] = ERPAdapter(provider=provider, base_url=base_url,
                                                      api_key=api_key, tool_name=tool_name)
                    continue
                except Exception as e:
                    print(f"[registry] ERPAdapter yüklenemedi ({tool_name}): {e} → simulated fallback")
            else:
                print(f"[registry] ERP secrets eksik ({tool_name}) → simulated fallback")

        elif adapter_class == "WhatsAppAdapter":
            if sec.resolver.available("whatsapp"):
                try:
                    from .adapters.whatsapp import WhatsAppAdapter
                    token = sec.resolver.inject("whatsapp")["token"]
                    phone_number_id = sec.resolver.inject("whatsapp").get("phone_number_id", "")
                    registry[tool_name] = WhatsAppAdapter(token=token, phone_number_id=phone_number_id)
                    continue
                except Exception as e:
                    print(f"[registry] WhatsAppAdapter yüklenemedi: {e} → simulated fallback")
            else:
                print(f"[registry] WhatsApp secrets eksik → simulated fallback")

        # SimulatedAdapter (default / fallback)
        if tool_name in SIMULATED_ADAPTERS:
            registry[tool_name] = SIMULATED_ADAPTERS[tool_name]
        else:
            print(f"[registry] {tool_name} için adapter bulunamadı — atlandı")

    return registry


# Backward compat: eski HANDLERS dict (main.py geçişi için geçici köprü)
HANDLERS: dict = {}  # build_registry() sonrası doldurulur, doğrudan kullanılmaz
