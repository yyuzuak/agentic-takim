"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, ReferenceLine, Cell,
} from "recharts";
import {
  Eye, TrendingUp, TrendingDown, Minus, AlertTriangle, Activity, BarChart3,
} from "lucide-react";
import {
  getObserverScores, getObserverClusters, getObserverRecommendations,
  type ObserverWindow,
} from "../lib/api";
import { cn } from "../lib/utils";
import { Card } from "../components/ui/card";
import { Badge, type BadgeProps } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";

const WINDOWS: ObserverWindow[] = ["1h", "24h", "7d"];

function scoreToken(v: number): { text: string; border: string; hsl: string } {
  if (v >= 0.8) return { text: "text-success", border: "border-success/40", hsl: "--success" };
  if (v >= 0.6) return { text: "text-warning", border: "border-warning/40", hsl: "--warning" };
  return { text: "text-destructive", border: "border-destructive/40", hsl: "--destructive" };
}

const SEVERITY_VARIANT: Record<string, BadgeProps["variant"]> = {
  critical: "danger", warning: "warning", info: "info",
};

const SCORE_LABELS: Record<string, string> = {
  overall_score: "Genel", workflow_score: "Workflow", tool_score: "Tool",
  planner_score: "Planner", retry_health: "Retry Sağlığı",
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

function cssVar(name: string): string {
  if (typeof window === "undefined") return "#888";
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v ? `hsl(${v})` : "#888";
}

// Tema değişiminde Recharts renklerini yeniden çöz.
function useChartColors() {
  const { theme } = useTheme();
  const [c, setC] = useState({ success: "#22c55e", warning: "#eab308", danger: "#ef4444", muted: "#888", primary: "#3b82f6", border: "#333" });
  useEffect(() => {
    const t = setTimeout(() => setC({
      success: cssVar("--success"), warning: cssVar("--warning"), danger: cssVar("--destructive"),
      muted: cssVar("--muted-foreground"), primary: cssVar("--primary"), border: cssVar("--border"),
    }), 0);
    return () => clearTimeout(t);
  }, [theme]);
  return c;
}

function DeltaBadge({ value }: { value: number | undefined }) {
  if (value === undefined) return null;
  const Icon = value > 0.001 ? TrendingUp : value < -0.001 ? TrendingDown : Minus;
  const color = value > 0.001 ? "text-success" : value < -0.001 ? "text-destructive" : "text-muted-foreground";
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-xs tabular-nums", color)}>
      <Icon className="w-3 h-3" />
      {value >= 0 ? "+" : ""}{(value * 100).toFixed(1)}%
    </span>
  );
}

export default function ObserverPage() {
  const [window, setWindow] = useState<ObserverWindow>("24h");
  const colors = useChartColors();

  const { data: scores } = useQuery({
    queryKey: ["observer-scores", window], queryFn: () => getObserverScores(window), refetchInterval: 5000,
  });
  const { data: clusters } = useQuery({
    queryKey: ["observer-clusters", window], queryFn: () => getObserverClusters(window), refetchInterval: 5000,
  });
  const { data: recs } = useQuery({
    queryKey: ["observer-recommendations", window], queryFn: () => getObserverRecommendations(window), refetchInterval: 5000,
  });
  // 3-window trend (seçili pencereden bağımsız)
  const trend = useQuery({
    queryKey: ["observer-trend"],
    queryFn: async () => {
      const [a, b, c] = await Promise.all(WINDOWS.map(w => getObserverScores(w)));
      return WINDOWS.map((w, i) => ({
        window: w, overall: [a, b, c][i].scores.overall_score * 100,
      }));
    },
    refetchInterval: 15000,
  });

  const s = scores?.scores;
  const delta = scores?.delta ?? null;
  const toolDetail = scores?.tool_detail ?? {};
  const toolBars = Object.entries(toolDetail).map(([tool, v]) => ({ tool, value: Math.round(v * 100) }));

  return (
    <div>
      <div className="flex items-start justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight flex items-center gap-2">
            <Eye className="w-5 h-5 text-muted-foreground" /> Observer Dashboard
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Post-hoc analytics plane · read-only
            {scores && (
              <span className="ml-2 tabular-nums">
                · {scores.samples} görev örneklemi
                {scores.requested_window !== scores.window && (
                  <span className="text-warning"> (fallback: {scores.window})</span>
                )}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1 shadow-card">
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

      {/* Score Cards */}
      <section className="mb-6">
        {!s && <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">{[0,1,2,3,4].map(i => <Skeleton key={i} className="h-24" />)}</div>}
        {s && (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {Object.entries(SCORE_LABELS).map(([key, label]) => {
              const v = s[key as keyof typeof s];
              const tok = scoreToken(v);
              return (
                <Card key={key} className={cn("p-4", tok.border)}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-muted-foreground">{label}</span>
                    <DeltaBadge value={delta?.[key]} />
                  </div>
                  <p className={cn("text-2xl font-bold tabular-nums", tok.text)}>{(v * 100).toFixed(0)}%</p>
                </Card>
              );
            })}
          </div>
        )}
        {delta === null && scores && (
          <p className="text-xs text-muted-foreground mt-2">
            Δ trend: veri yetersiz (her iki pencerede ≥50 örneklem gerekir)
          </p>
        )}
      </section>

      {/* Charts */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <Card className="p-4">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Tool Güvenilirliği</h2>
          </div>
          {toolBars.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Veri yok.</p>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(180, toolBars.length * 38)}>
              <BarChart data={toolBars} layout="vertical" margin={{ left: 12, right: 16 }}>
                <CartesianGrid horizontal={false} stroke={colors.border} />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: colors.muted, fontSize: 11 }} />
                <YAxis type="category" dataKey="tool" width={90} tick={{ fill: colors.muted, fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: cssVar("--card"), border: `1px solid ${colors.border}`, borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => [`${v}%`, "güvenilirlik"]}
                />
                <ReferenceLine x={80} stroke={colors.warning} strokeDasharray="4 4" />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {toolBars.map((b, i) => (
                    <Cell key={i} fill={b.value >= 80 ? colors.success : b.value >= 60 ? colors.warning : colors.danger} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Genel Skor Trendi (1h / 24h / 7d)</h2>
          </div>
          {!trend.data ? (
            <Skeleton className="h-44 w-full" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trend.data} margin={{ left: 4, right: 16, top: 8 }}>
                <CartesianGrid stroke={colors.border} />
                <XAxis dataKey="window" tick={{ fill: colors.muted, fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: colors.muted, fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: cssVar("--card"), border: `1px solid ${colors.border}`, borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => [`${v.toFixed(0)}%`, "genel skor"]}
                />
                <Line type="monotone" dataKey="overall" stroke={colors.primary} strokeWidth={2.5} dot={{ r: 4, fill: colors.primary }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
      </section>

      {/* Raw KPI Table */}
      <section className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Activity className="w-4 h-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Ham Metrikler</h2>
        </div>
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              {scores && Object.entries(KPI_LABELS).map(([key, [label, fmt]]) => (
                <tr key={key} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-2.5 text-muted-foreground">{label}</td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums">{fmt(scores.kpis[key] ?? 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>

      {/* Failure Clusters */}
      <section className="mb-6">
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
          <Card className="overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50 text-xs text-muted-foreground">
                  <th className="text-left px-4 py-2.5 font-semibold">Küme</th>
                  <th className="text-right px-4 py-2.5 font-semibold">Adet</th>
                  <th className="text-right px-4 py-2.5 font-semibold">10dk</th>
                  <th className="text-right px-4 py-2.5 font-semibold">Yoğunluk</th>
                  <th className="text-right px-4 py-2.5 font-semibold">Severity</th>
                </tr>
              </thead>
              <tbody>
                {clusters.clusters.map(c => (
                  <tr key={c.name} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-2.5 font-mono">{c.name}</td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground tabular-nums">{c.count}</td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground tabular-nums">{c.count_last_10min}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-muted-foreground tabular-nums">{c.cluster_strength}</td>
                    <td className="px-4 py-2.5 text-right">
                      <Badge variant={SEVERITY_VARIANT[c.severity] ?? "info"}>{c.severity}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
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
            <Card key={r.id} className="p-4">
              <div className="flex items-start gap-3">
                <Badge variant={SEVERITY_VARIANT[r.severity] ?? "info"} className="shrink-0">{r.severity}</Badge>
                <div className="min-w-0 flex-1">
                  <p className="text-sm">{r.message}</p>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <span className="text-xs text-muted-foreground font-mono">{r.target}</span>
                    {r.linked_kpis.map(k => (
                      <span key={k} className="text-xs bg-muted text-muted-foreground rounded px-1.5 py-0.5">{k}</span>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
