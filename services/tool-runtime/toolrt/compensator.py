"""Compensation kaydı — v0.9.1, INV-1

Kriter (GR-1): tool.side_effect==true AND tool.compensation is not None.
Kayıt atomic: aynı transaction'da çalışır (dışarıdan commit).
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import ToolCompensation


async def record_if_needed(
    s, exec_id: str, task_id: str, node_key: str, tool: str, args: dict, catalog: dict,
) -> None:
    spec = (catalog.get("tools") or {}).get(tool)
    if not spec:
        return
    if not spec.get("side_effect"):
        return
    compensate_fn = spec.get("compensation")
    stmt = pg_insert(ToolCompensation).values(
        id=str(uuid4()),
        task_id=task_id,
        node_key=node_key,
        tool=tool,
        exec_id=exec_id,
        compensate_fn=compensate_fn,
        compensate_args=args if compensate_fn else None,
        status="pending",
    ).on_conflict_do_nothing(index_elements=["exec_id"])
    await s.execute(stmt)
