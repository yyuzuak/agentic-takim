"""Clusterer — rule-based failure clustering + burst strength + severity escalation.

Kaynak: tool_invocations.error_code + task_nodes.error_code + memory_entries.success_score.
cluster_strength = count_last_10min / unique_tasks_last_10min (burst yoğunluğu).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import (
    MemoryEntry, Task, TaskNode, ToolInvocation, bounded_query, window_since,
)

_SEVERITY_ORDER = ["info", "warning", "critical"]
_BASE_SEVERITY = {
    "CIRCUIT_OPEN": "critical",
    "RATE_LIMIT": "warning",
    "ERP_TRANSIENT": "warning",
    "WHATSAPP_RATE_LIMIT": "warning",
    "SCHEMA_ERROR": "warning",
    "PERMISSION_DENIED": "critical",
    "MEMORY_LOW_CONFIDENCE": "info",
}


def _escalate(sev: str) -> str:
    idx = _SEVERITY_ORDER.index(sev) if sev in _SEVERITY_ORDER else 0
    return _SEVERITY_ORDER[min(idx + 1, len(_SEVERITY_ORDER) - 1)]


def _classify_tool(error_code: str | None, tool: str | None) -> str | None:
    if not error_code:
        return None
    if error_code == "CIRCUIT_OPEN":
        return "CIRCUIT_OPEN"
    if error_code == "RATE_LIMIT":
        if tool == "send_whatsapp":
            return "WHATSAPP_RATE_LIMIT"
        return "RATE_LIMIT"
    if error_code == "TRANSIENT" and tool and tool.startswith("erp"):
        return "ERP_TRANSIENT"
    if error_code == "SCHEMA":
        return "SCHEMA_ERROR"
    if error_code == "PERMISSION":
        return "PERMISSION_DENIED"
    return None


def _classify_node(error_code: str | None) -> str | None:
    if not error_code:
        return None
    return {
        "CIRCUIT_OPEN": "CIRCUIT_OPEN",
        "RATE_LIMIT": "RATE_LIMIT",
        "SCHEMA": "SCHEMA_ERROR",
        "PERMISSION": "PERMISSION_DENIED",
    }.get(error_code)


async def compute_clusters(session: AsyncSession, window: str) -> list[dict[str, Any]]:
    since = window_since(window)
    counts: dict[str, int] = {}
    last_seen: dict[str, datetime] = {}

    # tool_invocations
    inv_rows = (await bounded_query(
        session,
        select(ToolInvocation.error_code, ToolInvocation.tool,
               ToolInvocation.task_id, ToolInvocation.created_at),
        created_at_col=ToolInvocation.created_at, since=since,
    )).all()
    for r in inv_rows:
        name = _classify_tool(r.error_code, r.tool)
        if name:
            counts[name] = counts.get(name, 0) + 1
            if name not in last_seen or r.created_at > last_seen[name]:
                last_seen[name] = r.created_at

    # task_nodes (Task join — created_at tasks'tan)
    node_rows = (await bounded_query(
        session,
        select(TaskNode.error_code, Task.created_at).join(Task, TaskNode.task_id == Task.id),
        created_at_col=Task.created_at, since=since,
    )).all()
    for r in node_rows:
        name = _classify_node(r.error_code)
        if name:
            counts[name] = counts.get(name, 0) + 1
            if name not in last_seen or r.created_at > last_seen[name]:
                last_seen[name] = r.created_at

    # memory_entries → MEMORY_LOW_CONFIDENCE
    mem_rows = (await bounded_query(
        session,
        select(MemoryEntry.success_score, MemoryEntry.created_at),
        created_at_col=MemoryEntry.created_at, since=since,
    )).all()
    for r in mem_rows:
        if (r.success_score or 1.0) < 0.5:
            counts["MEMORY_LOW_CONFIDENCE"] = counts.get("MEMORY_LOW_CONFIDENCE", 0) + 1
            if "MEMORY_LOW_CONFIDENCE" not in last_seen or r.created_at > last_seen["MEMORY_LOW_CONFIDENCE"]:
                last_seen["MEMORY_LOW_CONFIDENCE"] = r.created_at

    if not counts:
        return []

    # Burst metrikleri — sabit 10 dakikalık pencere (window'dan bağımsız).
    ten_min_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    burst_counts, burst_tasks = await _burst_window(session, ten_min_ago)

    clusters = []
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        c10 = burst_counts.get(name, 0)
        unique_tasks = max(burst_tasks.get(name, 0), 1)
        strength = round(c10 / unique_tasks, 3)
        severity = _BASE_SEVERITY.get(name, "info")
        if c10 > 3:
            severity = _escalate(severity)
        clusters.append({
            "name": name,
            "count": count,
            "count_last_10min": c10,
            "cluster_strength": strength,
            "severity": severity,
            "last_seen": last_seen[name].isoformat() if name in last_seen else None,
        })
    return clusters


async def _burst_window(session: AsyncSession, since: datetime) -> tuple[dict[str, int], dict[str, int]]:
    """Son 10 dakikadaki cluster sayıları + benzersiz task sayıları."""
    counts: dict[str, int] = {}
    task_sets: dict[str, set] = {}

    inv_rows = (await bounded_query(
        session,
        select(ToolInvocation.error_code, ToolInvocation.tool, ToolInvocation.task_id,
               ToolInvocation.created_at),
        created_at_col=ToolInvocation.created_at, since=since,
    )).all()
    for r in inv_rows:
        name = _classify_tool(r.error_code, r.tool)
        if name:
            counts[name] = counts.get(name, 0) + 1
            task_sets.setdefault(name, set()).add(r.task_id)

    node_rows = (await bounded_query(
        session,
        select(TaskNode.error_code, TaskNode.task_id, Task.created_at)
        .join(Task, TaskNode.task_id == Task.id),
        created_at_col=Task.created_at, since=since,
    )).all()
    for r in node_rows:
        name = _classify_node(r.error_code)
        if name:
            counts[name] = counts.get(name, 0) + 1
            task_sets.setdefault(name, set()).add(r.task_id)

    return counts, {k: len(v) for k, v in task_sets.items()}
