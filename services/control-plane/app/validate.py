"""Şema + agent registry doğrulaması. `make validate` ve CI çağırır.

Doğrular:
  1. config/agents.json → Registry şemasına uyuyor mu.
  2. Kanonik NATS subject listesi events.v1 ile tutarlı mı.
  3. Her skill bir ajana bağlı mı (orphan skill yok).
  4. ACP tipli mesaj modelleri yüklenip örneklenebiliyor mu.
"""
from __future__ import annotations

import json
import sys
import time
from uuid import uuid4

from agentic_schemas.agent_registry.v1 import Registry
from agentic_schemas.events.v1 import ALL_SUBJECTS

from .config import settings

EXPECTED_SUBJECTS = [
    "ACP.TASK.CREATED",
    "ACP.TASK.COMPLETED",
    "ACP.TASK.FAILED",
    "ACP.TASK.DLQ",
    "ACP.TOOL.REQUEST",
    "ACP.TOOL.RESULT",
    "ACP.HANDOFF.REQUESTED",
    "ACP.AGENT.HEARTBEAT",
    "ACP.SYSTEM.EVENT",
]


def main() -> int:
    errors: list[str] = []

    # 1) Registry şeması
    try:
        with open(settings.config_path, encoding="utf-8") as f:
            raw = json.load(f)
        raw.pop("$comment", None)
        registry = Registry.model_validate(raw)
        print(f"✓ agents.json geçerli ({len(registry.agents)} ajan).")
    except Exception as e:  # noqa: BLE001
        errors.append(f"agents.json doğrulanamadı: {e}")
        registry = None

    # 2) Subject tutarlılığı
    if sorted(ALL_SUBJECTS) != sorted(EXPECTED_SUBJECTS):
        errors.append(f"NATS subject listesi tutarsız: {ALL_SUBJECTS} != {EXPECTED_SUBJECTS}")
    else:
        print("✓ Kanonik NATS subject'leri tutarlı.")

    # 3) Orphan skill kontrolü
    if registry is not None:
        mapping = registry.skill_to_agent()
        meta_skills = {s for a in registry.agents.values() if a.type.value == "meta" for s in a.skills}
        non_meta = {s for a in registry.agents.values() if a.type.value != "meta" for s in a.skills}
        orphan = non_meta - set(mapping)
        if orphan:
            errors.append(f"Routing'e bağlanamayan skill'ler: {orphan}")
        else:
            print(f"✓ {len(non_meta)} routable skill + {len(meta_skills)} meta skill eşlendi.")

    # 4) ACP mesaj modelleri yüklenip örneklenebiliyor mu
    try:
        from agentic_schemas.acp.v1 import (
            AckMessage,
            ErrorCode,
            ErrorMessage,
            HandoffMessage,
            ResultMessage,
            TaskMessage,
        )

        common = {"trace_id": uuid4(), "from": "kaptan", "to": "mimar", "timestamp": int(time.time())}
        TaskMessage(**common, skill="api-sozlesme-tasarimci", payload={"goal": "API tasarla"})
        ResultMessage(**common, payload={"result": {}, "confidence": 0.9})
        HandoffMessage(**common, payload={"reason": "teknik derinlik"})
        ErrorMessage(**common, error_code=ErrorCode.SCHEMA, message="eksik alan")
        AckMessage(**common)
        # v0.9.1: RATE_LIMIT ErrorCode
        assert ErrorCode.RATE_LIMIT == "RATE_LIMIT", "RATE_LIMIT eksik"
        # v1.1-c: CIRCUIT_OPEN ErrorCode
        assert ErrorCode.CIRCUIT_OPEN == "CIRCUIT_OPEN", "CIRCUIT_OPEN eksik"
        print("✓ ACP mesaj modelleri (Task/Result/Handoff/Error/Ack) örneklendi.")
        print("✓ RATE_LIMIT + CIRCUIT_OPEN ErrorCode mevcut.")
    except Exception as e:  # noqa: BLE001
        errors.append(f"ACP mesaj modelleri doğrulanamadı: {e}")

    if errors:
        print("\n".join(f"✗ {e}" for e in errors), file=sys.stderr)
        return 1
    print("✓ Tüm doğrulamalar geçti.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
