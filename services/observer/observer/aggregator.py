"""Aggregator — 9 KPI'ı windowed olarak hesaplar.

Tüm DB erişimi `bounded_query()` üzerinden (INVARIANT 2). KPI'lar 10k satır sınırı
içinde Python'da agregasyon yapar — v1.3 ölçeği için yeterli, bounded.

MIN_SAMPLES cold-start fallback: birincil örneklem (tasks) < 50 ise window büyütülür.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import db
from .db import (
    MemoryEntry, Task, TaskNode, ToolCompensation, ToolInvocation,
    bounded_query, next_larger_window, window_since,
)

MIN_SAMPLES = 50


def _ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


async def _effective_window(session: AsyncSession, window: str) -> tuple[str, int]:
    """tasks örneklemi MIN_SAMPLES altındaysa window büyütülür (1h→24h→7d)."""
    cur = window
    while True:
        since = window_since(cur)
        rows = (await bounded_query(
            session, select(Task.id), created_at_col=Task.created_at, since=since
        )).all()
        count = len(rows)
        nxt = next_larger_window(cur)
        if count >= MIN_SAMPLES or nxt is None:
            return cur, count
        cur = nxt


async def _workflow_kpis(session: AsyncSession, since: datetime) -> dict[str, Any]:
    rows = (await bounded_query(
        session,
        select(Task.status, Task.created_at, Task.updated_at),
        created_at_col=Task.created_at, since=since,
    )).all()
    total = len(rows)
    done = [r for r in rows if r.status == "done"]
    failed = sum(1 for r in rows if r.status in ("failed", "error"))
    durations = [
        (r.updated_at - r.created_at).total_seconds()
        for r in done if r.updated_at and r.created_at
    ]
    return {
        "workflow_success_rate": _ratio(len(done), total),
        "avg_workflow_duration_s": (sum(durations) / len(durations)) if durations else 0.0,
        "planner_error_rate": _ratio(failed, total),
        "_task_samples": total,
    }


async def _node_kpis(session: AsyncSession, since: datetime) -> dict[str, Any]:
    # task_nodes'ta created_at yok → tasks join, tasks.created_at ile window.
    stmt = (
        select(TaskNode.status, TaskNode.retry_count, TaskNode.max_retries, TaskNode.error_code)
        .join(Task, TaskNode.task_id == Task.id)
    )
    rows = (await bounded_query(
        session, stmt, created_at_col=Task.created_at, since=since
    )).all()
    total = len(rows)
    failed_nodes = [r for r in rows if r.status in ("failed", "error", "timeout")]
    failed_with_retry = sum(1 for r in failed_nodes if (r.retry_count or 0) > 0)
    retry_depths = [r.retry_count or 0 for r in failed_nodes]
    dlq = sum(
        1 for r in rows
        if r.error_code is not None and (r.retry_count or 0) >= (r.max_retries or 0)
    )
    return {
        "retry_coverage": _ratio(failed_with_retry, len(failed_nodes)),
        "retry_pressure": (sum(retry_depths) / len(retry_depths)) if retry_depths else 0.0,
        "dlq_rate": _ratio(dlq, total),
        "_node_samples": total,
    }


async def _tool_kpis(session: AsyncSession, since: datetime) -> dict[str, Any]:
    rows = (await bounded_query(
        session,
        select(ToolInvocation.tool, ToolInvocation.status),
        created_at_col=ToolInvocation.created_at, since=since,
    )).all()
    per_tool: dict[str, dict[str, int]] = {}
    for r in rows:
        t = per_tool.setdefault(r.tool, {"success": 0, "total": 0})
        t["total"] += 1
        if r.status == "success":
            t["success"] += 1

    # Bayesian smoothing (Jeffreys prior α=β=1) + invocation-count weighted avg.
    detail: dict[str, float] = {}
    weighted_num = weighted_den = 0.0
    for tool, c in per_tool.items():
        smoothed = (c["success"] + 1) / (c["total"] + 2)
        detail[tool] = round(smoothed, 4)
        weighted_num += smoothed * c["total"]
        weighted_den += c["total"]
    return {
        "tool_reliability": _ratio(weighted_num, weighted_den) if weighted_den else 1.0,
        "_tool_detail": detail,
        "_tool_invocations": int(weighted_den),
    }


async def _memory_kpis(session: AsyncSession, since: datetime) -> dict[str, Any]:
    rows = (await bounded_query(
        session,
        select(MemoryEntry.retrieval_count, MemoryEntry.reuse_success_count),
        created_at_col=MemoryEntry.created_at, since=since,
    )).all()
    reuse = sum(r.reuse_success_count or 0 for r in rows)
    retr = sum(r.retrieval_count or 0 for r in rows)
    return {"memory_reuse_success": _ratio(reuse, retr)}


async def _compensation_kpis(session: AsyncSession, since: datetime) -> dict[str, Any]:
    comps = (await bounded_query(
        session, select(ToolCompensation.id),
        created_at_col=ToolCompensation.created_at, since=since,
    )).all()
    invocs = (await bounded_query(
        session, select(ToolInvocation.id),
        created_at_col=ToolInvocation.created_at, since=since,
    )).all()
    return {"compensation_rate": _ratio(len(comps), len(invocs))}


async def compute_kpis(session: AsyncSession, window: str) -> dict[str, Any]:
    """9 KPI + örneklem sayıları + effective window. MIN_SAMPLES fallback uygulanır."""
    eff_window, task_samples = await _effective_window(session, window)
    since = window_since(eff_window)

    wf = await _workflow_kpis(session, since)
    nd = await _node_kpis(session, since)
    tl = await _tool_kpis(session, since)
    mem = await _memory_kpis(session, since)
    comp = await _compensation_kpis(session, since)

    kpis = {
        "workflow_success_rate": round(wf["workflow_success_rate"], 4),
        "avg_workflow_duration_s": round(wf["avg_workflow_duration_s"], 2),
        "planner_error_rate": round(wf["planner_error_rate"], 4),
        "retry_coverage": round(nd["retry_coverage"], 4),
        "retry_pressure": round(nd["retry_pressure"], 4),
        "dlq_rate": round(nd["dlq_rate"], 4),
        "tool_reliability": round(tl["tool_reliability"], 4),
        "memory_reuse_success": round(mem["memory_reuse_success"], 4),
        "compensation_rate": round(comp["compensation_rate"], 4),
    }
    return {
        "kpis": kpis,
        "tool_detail": tl["_tool_detail"],
        "requested_window": window,
        "effective_window": eff_window,
        "samples": task_samples,
        "node_samples": nd["_node_samples"],
    }
