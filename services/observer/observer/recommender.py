"""Recommender — eşik tabanlı advisory öneriler (v1.3: SADECE görünürlük, pasif).

linked_kpis: UI'da KPI→cluster→recommendation correlation view için.
v1.4'te bu öneriler planner prompt'una enjekte edilecek (Advise fazı). v1.3'te değil.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .clusterer import compute_clusters
from .scorer import compute_scores


async def compute_recommendations(session: AsyncSession, window: str = "24h") -> list[dict[str, Any]]:
    data = await compute_scores(session, window)
    kpis = data["kpis"]
    tool_detail: dict[str, float] = data["tool_detail"]
    eff_window = data["window"]
    recs: list[dict[str, Any]] = []

    tool_rel = kpis["tool_reliability"]
    if tool_rel < 0.80:
        # En zayıf tool'u hedef göster (varsa).
        target = min(tool_detail, key=tool_detail.get) if tool_detail else "tool"
        sev = "critical" if tool_rel < 0.60 else "warning"
        recs.append(_rec(
            "tool_reliability_low", sev, target,
            f"Tool güvenilirliği %{tool_rel*100:.0f} — circuit breaker config veya retry politikasını kontrol edin",
            tool_rel, 0.80, ["tool_reliability", "retry_pressure"], eff_window,
        ))

    if kpis["retry_pressure"] > 1.0:
        recs.append(_rec(
            "retry_pressure_high", "warning", "orchestrator",
            f"Ortalama retry derinliği {kpis['retry_pressure']:.2f} — kalıcı hata kaynağı olabilir",
            kpis["retry_pressure"], 1.0, ["retry_coverage", "retry_pressure"], eff_window,
        ))

    if kpis["workflow_success_rate"] < 0.70:
        recs.append(_rec(
            "workflow_success_low", "critical", "planner",
            f"Workflow başarı oranı %{kpis['workflow_success_rate']*100:.0f} — plan kalitesini gözden geçirin",
            kpis["workflow_success_rate"], 0.70, ["workflow_score", "planner_error_rate"], eff_window,
        ))

    if kpis["memory_reuse_success"] < 0.50:
        recs.append(_rec(
            "memory_reuse_low", "info", "memory",
            f"Hafıza yeniden kullanım başarısı %{kpis['memory_reuse_success']*100:.0f} — recall kalitesi düşük olabilir",
            kpis["memory_reuse_success"], 0.50, ["memory_score"], eff_window,
        ))

    if kpis["compensation_rate"] > 0.10:
        recs.append(_rec(
            "compensation_rate_high", "warning", "tool-runtime",
            f"Kompanzasyon oranı %{kpis['compensation_rate']*100:.0f} — tool çağrıları sık geri alınıyor",
            kpis["compensation_rate"], 0.10, ["tool_reliability", "compensation_rate"], eff_window,
        ))

    clusters = await compute_clusters(session, eff_window)
    for c in clusters:
        if c["name"] == "CIRCUIT_OPEN" and c["severity"] == "critical":
            recs.append(_rec(
                "circuit_open_critical", "critical", "tool-runtime",
                f"CIRCUIT_OPEN burst tespit edildi (strength={c['cluster_strength']}) — adapter down olabilir",
                float(c["count"]), 0.0, ["tool_reliability"], eff_window,
            ))
    return recs


def _rec(rec_id, severity, target, message, value, threshold, linked, window) -> dict[str, Any]:
    return {
        "id": rec_id,
        "severity": severity,
        "target": target,
        "message": message,
        "metric_value": round(float(value), 4),
        "threshold": threshold,
        "linked_kpis": linked,
        "window": window,
    }
