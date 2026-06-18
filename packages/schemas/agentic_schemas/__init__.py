"""Agentic Takım paylaşılan sözleşmeleri.

Versiyonlu alt modüller (schema versioning):
  - acp.v1            → mesaj zarfı, mesaj tipleri (ACP.md)
  - skill_contract.v1 → skill sözleşmesi (CLAUDE.md Bölüm 6)
  - agent_registry.v1 → ajan/skill registry (ARCHITECTURE.md Bölüm 5)
  - events.v1         → JetStream subject'leri + event modelleri (ACP.md Bölüm 6)
"""

__all__ = ["acp", "skill_contract", "agent_registry", "events"]
