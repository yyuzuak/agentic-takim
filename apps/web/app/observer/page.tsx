"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getObserverScores, getObserverClusters, getObserverRecommendations,
  type ObserverWindow,
} from "../lib/api";
import { cn, timeAgo } from "../lib/utils";
import { Eye, TrendingUp, TrendingDown, Minus, AlertTriangle, Activity } from "lucide-react";

const WINDOWS: ObserverWindow[] = ["1h", "24h", "7d"];

function scoreColor(v: number): string {
  if (v >= 0.8) return "text-emerald-400";
  if (v >= 0.6) return "text-amber-400";
  return "text-red-400";
}
function scoreBorder(v: number): string {
  if (v >= 0.8) return "border-emerald-800/50";
  if (v >= 0.6) return "border-amber-800/50";
  return "border-red-800/50";
}

const SEVERITY: Record<string, string> = {
  critical: "bg-red-950 text-red-400 border-red-800",
  warning: "bg-amber-950 text-amber-400 border-amber-800",
  info: "bg-blue-950 text-blue-400 border-blue-800",
};

const SCORE_LABELS: Record<string, string> = {
  overall_score: "Genel",
  workflow_score: "Workflow",
  tool_score: "Tool",
  planner_score: "Planner",
  retry_health: "Retry Sağlığı",
};

const KPI_LABELS: Record<string, [string, (v: number) => string]> = {
  workflow_success_rate: ["Workflow Başarı", v => `${(v * 100).toFixed(0)}%`],
  avg_workflow_duration_s: ["Ort. Süre", v => `${v.toFixed(1)}s`],
  planner_error_rate: ["Planner Hata", v => `${(v * 100).toFixed(0)}%`],
  retry_coverage: ["Retry Kapsama", v => `${(v * 100).toFixed(0)}%`],
  retry_pressure: ["Retry Baskısı", v => v.toFixed(2)],
  dlq_rate: ["DLQ Oranı", v => `${(v * 100).toFixed(0)}%`],
  tool_reliability: ["Tool Güvenilirlik", v => `${(v * 100).toFixed(0)}%`],
  memory_reuse_success: ["Hafıza Tekrar", v => `${(v * 100).toFixed(0)}%`],
  compensation_rate: ["Kompanzasyon", v => `${(v * 100).toFixed(0)}%`],
};

function DeltaBadge({ value }: { value: number | undefined }) {
  if (value === undefined) return null;
  const Icon = value > 0.001 ? TrendingUp : value < -0.001 ? TrendingDown : Minus;
  const color = value > 0.001 ? "text-emerald-400" : value < -0.001 ? "text-red-400" : "text-muted-foreground";
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-xs", color)}>
      <Icon className="w-3 h-3" />
      {value >= 0 ? "+" : ""}{(value * 100).toFixed(1)}%
    </span>
  );
}

export default function ObserverPage() {
  const [window, setWindow] = useState<ObserverWindow>("24h");

  const { data: scores } = useQuery({
    queryKey: ["observer-scores", window],
    queryFn: () => getObserverScores(window),
    refetchInterval: 5000,
  });
  const { data: clusters } = useQuery({
    queryKey: ["observer-clusters", window],
    queryFn: () => getObserverClusters(window),
    refetchInterval: 5000,
  });
  const { data: recs } = useQuery({
    queryKey: ["observer-recommendations", window],
    queryFn: () => getObserverRecommendations(window),
    refetchInterval: 5000,
  });

  const s = scores?.scores;
  const delta = scores?.delta ?? null;

  return (
    <div>
      <div className="flex items-start justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <Eye className="w-5 h-5 text-muted-foreground" />
            Observer Dashboard
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Post-hoc analytics plane · read-only
            {scores && (
              <span className="ml-2">
                · {scores.samples} görev örneklemi
                {scores.requested_window !== scores.window && (
                  <span className="text-amber-400"> (fallback: {scores.window})</span>
                )}
              </span>
            )}
          </p>
        </div>
        {/* Window Selector */}
        <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1">
          {WINDOWS.map(w => (
            <button
              key={w}
              onClick={() => setWindow(w)}
              className={cn(
                "px-3 py-1 rounded-md text-xs font-medium transition-colors",
                window === w ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {w}
            </button>
          ))}
        </div>
      </div>

      {/* Score Cards (composite only) */}
      <section className="mb-8">
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {s && Object.entries(SCORE_LABELS).map(([key, label]) => {
            const v = s[key as keyof typeof s];
            return (
              <div key={key} className={cn("rounded-xl border bg-card p-4", scoreBorder(v))}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-muted-foreground">{label}</span>
                  <DeltaBadge value={delta?.[key]} />
                </div>
                <p className={cn("text-2xl font-bold", scoreColor(v))}>{(v * 100).toFixed(0)}%</p>
              </div>
            );
          })}
        </div>
        {delta === null && scores && (
          <p className="text-xs text-muted-foreground mt-2">
            Δ trend: veri yetersiz (delta için her iki pencerede ≥50 örneklem gerekir)
          </p>
        )}
      </section>

      {/* Raw KPI Table (raw metrics only) */}
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <Activity className="w-4 h-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Ham Metrikler</h2>
        </div>
        <div className="rounded-xl border border-border overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              {scores && Object.entries(KPI_LABELS).map(([key, [label, fmt]]) => (
                <tr key={key} className="border-b border-border last:border-0 hover:bg-muted/20">
                  <td className="px-4 py-2.5 text-muted-foreground">{label}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-foreground">
                    {fmt(scores.kpis[key] ?? 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Failure Clusters */}
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="w-4 h-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Hata Kümeleri</h2>
        </div>
        {clusters && clusters.clusters.length === 0 && (
          <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            Bu pencerede hata kümesi yok.
          </div>
        )}
        {clusters && clusters.clusters.length > 0 && (
          <div className="rounded-xl border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30 text-xs text-muted-foreground">
                  <th className="text-left px-4 py-2.5 font-semibold">Küme</th>
                  <th className="text-right px-4 py-2.5 font-semibold">Adet</th>
                  <th className="text-right px-4 py-2.5 font-semibold">10dk</th>
                  <th className="text-right px-4 py-2.5 font-semibold">Yoğunluk</th>
                  <th className="text-right px-4 py-2.5 font-semibold">Severity</th>
                </tr>
              </thead>
              <tbody>
                {clusters.clusters.map(c => (
                  <tr key={c.name} className="border-b border-border last:border-0 hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-mono text-foreground">{c.name}</td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">{c.count}</td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">{c.count_last_10min}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{c.cluster_strength}</td>
                    <td className="px-4 py-2.5 text-right">
                      <span className={cn("inline-block px-2 py-0.5 rounded border text-xs", SEVERITY[c.severity] ?? SEVERITY.info)}>
                        {c.severity}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Recommendations */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Öneriler (advisory)</h2>
        </div>
        {recs && recs.recommendations.length === 0 && (
          <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            Eşik aşan öneri yok — sistem sağlıklı görünüyor.
          </div>
        )}
        <div className="flex flex-col gap-2">
          {recs?.recommendations.map(r => (
            <div key={r.id} className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-start gap-3">
                <span className={cn("inline-block px-2 py-0.5 rounded border text-xs shrink-0", SEVERITY[r.severity] ?? SEVERITY.info)}>
                  {r.severity}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-foreground">{r.message}</p>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <span className="text-xs text-muted-foreground font-mono">{r.target}</span>
                    {r.linked_kpis.map(k => (
                      <span key={k} className="text-xs bg-muted text-muted-foreground rounded px-1.5 py-0.5">{k}</span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
