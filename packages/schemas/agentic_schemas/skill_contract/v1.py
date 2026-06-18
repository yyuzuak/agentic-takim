"""Skill Contract v1 — CLAUDE.md Bölüm 6.

Her skill bu sözleşmeye uymak zorundadır.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Determinism(str, Enum):
    HIGH = "yuksek"
    MEDIUM = "orta"
    LOW = "dusuk"


class TokenCost(str, Enum):
    LOW = "dusuk"
    MEDIUM = "orta"
    HIGH = "yuksek"


class SkillContract(BaseModel):
    ad: str = Field(description="Benzersiz kebab-case skill kimliği")
    girdi_sema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema")
    cikti_sema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema")
    bagimliliklar: list[str] = Field(default_factory=list, description="Önce çalışması gereken skill'ler")
    determinizm: Determinism = Determinism.MEDIUM
    token_maliyeti: TokenCost = TokenCost.MEDIUM
    hata_modlari: list[str] = Field(default_factory=list)
