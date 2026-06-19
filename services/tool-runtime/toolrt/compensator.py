"""Compensation motoru — v1.1-b

record_if_needed(): INV-1 — tool.side_effect+compensation → pending kayıt.
apply(): Adapter.compensate() → DB güncelle (applied | failed).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
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


async def apply(s, exec_id: str, registry: dict, actor: str = "system") -> dict:
    """
    Bekleyen compensation'ı uygula.
    registry: tool_name → ToolAdapter (main.py'den geçirilir)
    Dönüş: {"exec_id", "status", "result"}
    """
    row = (await s.execute(
        select(ToolCompensation).where(ToolCompensation.exec_id == exec_id)
    )).scalars().first()

    if row is None:
        return {"exec_id": exec_id, "status": "not_found", "result": None}

    if row.status == "applied":
        return {"exec_id": exec_id, "status": "already_applied", "result": row.applied_result}

    adapter = registry.get(row.tool)
    if adapter is None:
        row.status = "failed"
        row.applied_result = {"error": f"no adapter for tool '{row.tool}'"}
        row.applied_at = datetime.now(timezone.utc)
        await s.commit()
        return {"exec_id": exec_id, "status": "failed", "result": row.applied_result}

    try:
        result = await adapter.compensate(row.compensate_args or {}, exec_id)
        if result.get("reversible") is False and "error" in result:
            row.status = "failed"
        else:
            row.status = "applied"
        row.applied_result = result
        row.applied_at = datetime.now(timezone.utc)
    except Exception as e:  # noqa: BLE001
        row.status = "failed"
        row.applied_result = {"error": str(e)}
        row.applied_at = datetime.now(timezone.utc)

    await s.commit()
    return {"exec_id": exec_id, "status": row.status, "result": row.applied_result}
