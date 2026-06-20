"use client";
import { useQuery } from "@tanstack/react-query";
import { getAdapterHealth, getToolCapabilities } from "../lib/api";
import { StatusBadge } from "../components/status-badge";
import { Activity, Zap, Shield } from "lucide-react";

function AdapterCard({ adapter, status, latency_ms, detail }: {
  adapter: string; status: string; latency_ms: number | null; detail: string | null;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold capitalize">{adapter}</h3>
        <StatusBadge status={status} />
      </div>
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        {latency_ms !== null && (
          <span className="flex items-center gap-1">
            <Activity className="w-3 h-3" />
            {latency_ms}ms
          </span>
        )}
        {detail && <span className="truncate">{detail}</span>}
      </div>
    </div>
  );
}

export default function ToolsPage() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["adapter-health"],
    queryFn: getAdapterHealth,
    refetchInterval: 2000,
  });
  const { data: caps } = useQuery({
    queryKey: ["tool-capabilities"],
    queryFn: getToolCapabilities,
    refetchInterval: 10000,
  });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Tool Center</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Adapter sağlığı ve yetenekleri · 2s refresh</p>
      </div>

      {/* Adapter health grid */}
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-4 h-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Adapter Health</h2>
        </div>
        {healthLoading && <p className="text-sm text-muted-foreground">Yükleniyor…</p>}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {health?.adapters.map(a => (
            <AdapterCard key={a.adapter} {...a} />
          ))}
        </div>
      </section>

      {/* Capabilities table */}
      {caps && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Tool Yetenekleri</h2>
          </div>
          <div className="rounded-xl border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground">Tool</th>
                  <th className="text-center px-4 py-2.5 text-xs font-semibold text-muted-foreground">dry_run</th>
                  <th className="text-center px-4 py-2.5 text-xs font-semibold text-muted-foreground">compensation</th>
                  <th className="text-center px-4 py-2.5 text-xs font-semibold text-muted-foreground">circuit_breaker</th>
                  <th className="text-center px-4 py-2.5 text-xs font-semibold text-muted-foreground">bulk</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(caps.tools).map(([tool, c]) => (
                  <tr key={tool} className="border-b border-border last:border-0 hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-mono text-foreground">{tool}</td>
                    {["dry_run", "compensation", "circuit_breaker", "bulk"].map(k => (
                      <td key={k} className="px-4 py-2.5 text-center">
                        {c[k]
                          ? <span className="text-emerald-400 text-base">✓</span>
                          : <span className="text-zinc-600 text-base">—</span>
                        }
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
