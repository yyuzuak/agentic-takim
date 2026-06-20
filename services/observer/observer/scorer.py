"""Scorer — KPI'ları composite kalite skoruna çevirir (0.0–1.0).

retry_health nonlinear (1/(1+x)). Anomaly delta noise-guarded: yalnız her iki
window'da da MIN_SAMPLES varsa hesaplanır, yoksa None.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .aggregator import MIN_SAMPLES, compute_kpis

WEIGHTS = {
    "workflow_score": 0.35,
    "tool_score": 0.30,
    "planner_score": 0.20,
    "retry_health": 0.15,
}


def _scores_from_kpis(kpis: dict[str, float]) -> dict[str, float]:
    workflow_score = kpis["workflow_success_rate"]
    tool_score = kpis["tool_reliability"]
    memory_score = kpis["memory_reuse_success"]
    planner_score = 1.0 - kpis["planner_error_rate"]
    retry_health = 1.0 / (1.0 + kpis["retry_pressure"])  # nonlinear decay

    overall = (
        workflow_score * WEIGHTS["workflow_score"]
        + tool_score * WEIGHTS["tool_score"]
        + planner_score * WEIGHTS["planner_score"]
        + retry_health * WEIGHTS["retry_health"]
    )
    return {
        "overall_score": round(overall, 4),
        "workflow_score": round(workflow_score, 4),
        "tool_score": round(tool_score, 4),
        "memory_score": round(memory_score, 4),
        "planner_score": round(planner_score, 4),
        "retry_health": round(retry_health, 4),
    }


async def compute_scores(session: AsyncSession, window: str) -> dict[str, Any]:
    """Composite skorlar + raw KPI + noise-guarded delta (vs 24h baseline)."""
    primary = await compute_kpis(session, window)
    scores = _scores_from_kpis(primary["kpis"])

    # Anomaly delta: kısa window skoru ile 24h baseline farkı.
    # Noise guard: (1) her iki window'da da MIN_SAMPLES, (2) effective window'lar
    # FARKLI olmalı — ikisi de aynı pencereye fallback olduysa delta yapay sıfırdır.
    delta = None
    if window != "24h":
        baseline = await compute_kpis(session, "24h")
        same_window = primary["effective_window"] == baseline["effective_window"]
        if (
            primary["samples"] >= MIN_SAMPLES
            and baseline["samples"] >= MIN_SAMPLES
            and not same_window
        ):
            base_scores = _scores_from_kpis(baseline["kpis"])
            delta = {k: round(scores[k] - base_scores[k], 4) for k in scores}

    return {
        "scores": scores,
        "kpis": primary["kpis"],
        "tool_detail": primary["tool_detail"],
        "delta": delta,
        "window": primary["effective_window"],
        "requested_window": primary["requested_window"],
        "samples": primary["samples"],
        "node_samples": primary["node_samples"],
    }
