"use client";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Minus, Activity, Zap, Shield } from "lucide-react";
import { getAdapterHealth, getToolCapabilities } from "../lib/api";
import { StatusBadge } from "../components/status-badge";
import { Card } from "../components/ui/card";
import { Table, THead, TBody, TR, TH, TD } from "../components/ui/table";
import { Skeleton } from "../components/ui/skeleton";

function AdapterCard({ adapter, status, latency_ms, detail }: {
  adapter: string; status: string; latency_ms: number | null; detail: string | null;
}) {
  return (
    <Card hover className="p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold capitalize">{adapter}</h3>
        <StatusBadge status={status} />
      </div>
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        {latency_ms !== null && (
          <span className="flex items-center gap-1 tabular-nums">
            <Activity className="w-3 h-3" /> {latency_ms}ms
          </span>
        )}
        {detail && <span className="truncate">{detail}</span>}
      </div>
    </Card>
  );
}

const CAP_KEYS = ["dry_run", "compensation", "circuit_breaker", "bulk"];

export default function ToolsPage() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["adapter-health"], queryFn: getAdapterHealth, refetchInterval: 2000,
  });
  const { data: caps } = useQuery({
    queryKey: ["tool-capabilities"], queryFn: getToolCapabilities, refetchInterval: 10000,
  });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Tool Center</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Adapter sağlığı ve yetenekleri · 2s refresh</p>
      </div>

      <section className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-4 h-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Adapter Health</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {healthLoading && [0, 1, 2, 3].map(i => <Skeleton key={i} className="h-24" />)}
          {health?.adapters.map(a => <AdapterCard key={a.adapter} {...a} />)}
        </div>
      </section>

      {caps && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Tool Yetenekleri</h2>
          </div>
          <Table>
            <THead>
              <tr>
                <TH>Tool</TH>
                {CAP_KEYS.map(k => <TH key={k} className="text-center">{k}</TH>)}
              </tr>
            </THead>
            <TBody>
              {Object.entries(caps.tools).map(([tool, c]) => (
                <TR key={tool}>
                  <TD className="font-mono">{tool}</TD>
                  {CAP_KEYS.map(k => (
                    <TD key={k} className="text-center">
                      {c[k]
                        ? <CheckCircle2 className="w-4 h-4 text-success inline" />
                        : <Minus className="w-4 h-4 text-muted-foreground/40 inline" />}
                    </TD>
                  ))}
                </TR>
              ))}
            </TBody>
          </Table>
        </section>
      )}
    </div>
  );
}
