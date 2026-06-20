"""Snapshot — build kimliği + DAG snapshot + build manifest (dosya envanteri).

Kimlik modeli (3 ayrı kavram):
  - build_fingerprint: içerik kimliği (task'tan bağımsız) — cross-task comparison/cache
  - build_id: kaydın benzersiz handle'ı (bld_<uuid12>)
  - build_number: task içi monotonik sayaç (UI "Build #N")
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

from . import ASSEMBLER_VERSION
from .validator import VALIDATOR_VERSION

_EXCLUDE = ("node_modules", ".next", "dist", "build", ".git")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact_hashes(artifacts: list[dict]) -> list[str]:
    """Her artifact content'inin deterministik sha256'sı (sıralı JSON)."""
    out = []
    for a in artifacts:
        canon = json.dumps(a.get("content"), sort_keys=True, ensure_ascii=False).encode()
        out.append(_sha256(canon))
    return out


def fingerprint(art_hashes: list[str]) -> str:
    """İçerik kimliği — task_id DAHİL DEĞİL (saf içerik → cross-task cache)."""
    raw = "|".join(sorted(art_hashes)) + ASSEMBLER_VERSION + VALIDATOR_VERSION
    return _sha256(raw.encode())[:16]


def new_build_id() -> str:
    return "bld_" + uuid.uuid4().hex[:12]


def dag_snapshot(task: dict, art_hashes: list[str]) -> dict:
    nodes = task.get("nodes") or task.get("plan") or []
    hmap = {}
    # artifact sırası nodes ile birebir değil; node_key→hash eşlemesi artifacts'tan gelir
    return {
        "nodes": [
            {"key": n.get("key"), "skill": n.get("skill"), "agent": n.get("agent"),
             "depends_on": n.get("depends_on", [])}
            for n in nodes
        ],
        "assembler_version": ASSEMBLER_VERSION,
        "artifact_count": len(art_hashes),
    }


def _file_inventory(repo: str) -> list[dict]:
    inv = []
    for dp, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE]
        for fn in files:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, repo)
            if rel.startswith(".build_manifest"):
                continue
            data = open(full, "rb").read()
            inv.append({"path": rel, "sha256": _sha256(data)[:16], "size": len(data)})
    return sorted(inv, key=lambda x: x["path"])


def write_manifest(repo: str, *, build_id: str, build_fingerprint: str, build_number: int,
                   task_id: str, validator_result: dict) -> dict:
    """Workspace köküne .build_manifest.json yazar; manifest dict'i döner."""
    manifest = {
        "build_id": build_id,
        "build_fingerprint": build_fingerprint,
        "build_number": build_number,
        "task_id": task_id,
        "assembler_version": ASSEMBLER_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "validator_result": validator_result["status"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": _file_inventory(repo),
    }
    with open(os.path.join(repo, ".build_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return manifest
