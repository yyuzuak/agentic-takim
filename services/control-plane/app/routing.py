"""Kaptan routing — skill → agent eşlemesi (ARCHITECTURE.md Bölüm 7).

Registry config'ten yüklenir; bilinmeyen/boş skill fallback olarak Kaptan'a gider.
"""
from __future__ import annotations

import json

from agentic_schemas.agent_registry.v1 import Registry

from .config import settings

_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        with open(settings.config_path, encoding="utf-8") as f:
            raw = json.load(f)
        raw.pop("$comment", None)
        _registry = Registry.model_validate(raw)
    return _registry


def route(skill: str | None) -> str:
    """Skill'i çalıştıracak ajanı döner; eşleşme yoksa 'kaptan' (fallback)."""
    if not skill:
        return "kaptan"
    return get_registry().skill_to_agent().get(skill, "kaptan")
