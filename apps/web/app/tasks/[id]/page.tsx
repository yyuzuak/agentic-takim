"use client";
import { useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getTask, getTaskTools, getTaskCompensations, getTaskEvents,
  approveNode, approveTask, applyCompensation,
  type NodeDetail,
} from "../../lib/api";
import { StatusBadge } from "../../components/status-badge";
import { DagView } from "./_dag";
import { Timeline } from "./_timeline";
import { timeAgo } from "../../lib/utils";
import { Loader2, RotateCcw, CheckCheck } from "lucide-react";

export default function TaskDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const qc = useQueryClient();
  const refetch = () => qc.invalidateQueries({ queryKey: ["task", id] });

  const { data: task, isLoading } = useQuery({
    queryKey: ["task", id],
    queryFn: () => getTask(id),
    refetchInterval: 2000,
  });
  const { data: toolData } = useQuery({
    queryKey: ["task-tools", id],
    queryFn: () => getTaskTools(id),
    refetchInterval: 2000,
  });
  const { data: compData } = useQuery({
    queryKey: ["task-compensations", id],
    queryFn: () => getTaskCompensations(id),
    refetchInterval: 4000,
  });
  const { data: evData } = useQuery({
    queryKey: ["task-events", id],
    queryFn: () => getTaskEvents(id),
    refetchInterval: 2000,
  });

  const approveMut = useMutation({
    mutationFn: (key: string) => approveNode(id, key),
    onSuccess: refetch,
  });
  const approveTaskMut = useMutation({
    mutationFn: () => approveTask(id),
    onSuccess: refetch,
  });
  const compMut = useMutation({
    mutationFn: (execId: string) => applyCompensation(id, execId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task-compensations", id] }),
  });

  const nodeMap = useMemo<Map<string, NodeDetail>>(() => {
    const m = new Map<string, NodeDetail>();
    task?.nodes?.forEach(n => m.set(n.key, n));
    return m;
  }, [task]);

  const pendingComps = compData?.compensations.filter(c => c.status === "pending" && c.compensate_fn) ?? [];
  const needsApproval = task?.status === "awaiting_approval";

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Yükleniyor…
      </div>
    );
  }

  if (!task) return <p className="text-muted-foreground">Görev bulunamadı.</p>;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <h1 className="text-base font-semibold text-foreground mb-1 leading-snug">{task.goal}</h1>
            <div className="flex items-center gap-3 flex-wrap">
              <StatusBadge status={task.status} />
              <span className="text-xs text-muted-foreground">{timeAgo(task.created_at)}</span>
              <span className="text-xs text-muted-foreground font-mono">{task.id.slice(0, 8)}</span>
            </div>
          </div>
          {needsApproval && (
            <button
              onClick={() => approveTaskMut.mutate()}
              disabled={approveTaskMut.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-black text-sm font-semibold px-4 py-2 transition-colors shrink-0"
            >
              {approveTaskMut.isPending
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <CheckCheck className="w-4 h-4" />}
              Onayla
            </button>
          )}
        </div>
      </div>

      {/* Main: DAG + Timeline side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* DAG */}
        <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-foreground">Yürütme Planı</h2>
          {task.plan?.length ? (
            <div style={{ height: 400 }}>
              <DagView
                plan={task.plan}
                nodeMap={nodeMap}
                onApproveNode={(key) => approveMut.mutate(key)}
              />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Plan henüz oluşturulmadı.</p>
          )}
        </div>

        {/* Timeline */}
        <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-foreground">Canlı İlerleme</h2>
          <div className="overflow-y-auto max-h-[400px] pr-1">
            <Timeline
              events={evData?.events ?? []}
              tools={toolData?.invocations ?? []}
              taskCreatedAt={task.created_at}
            />
          </div>
        </div>
      </div>

      {/* Tool Invocations */}
      {(toolData?.count ?? 0) > 0 && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold mb-3">Tool Çağrıları ({toolData!.count})</h2>
          <div className="flex flex-col gap-2">
            {toolData!.invocations.map((inv, i) => (
              <div key={i} className="rounded-lg border border-border bg-muted/30 px-3 py-2 flex items-center gap-3 flex-wrap">
                <StatusBadge status={inv.status} className="shrink-0" />
                <span className="text-sm font-mono text-foreground">{inv.tool}</span>
                <span className="text-xs text-muted-foreground">{inv.node_key}</span>
                {inv.dry_run && <span className="text-xs bg-blue-950 text-blue-400 border border-blue-800 rounded px-1.5 py-0.5">dry-run</span>}
                {inv.rate_limited && <span className="text-xs bg-orange-950 text-orange-400 border border-orange-800 rounded px-1.5 py-0.5">rate-limited</span>}
                {inv.result && (
                  <span className="text-xs text-muted-foreground ml-auto hidden lg:block truncate max-w-xs">
                    {Object.entries(inv.result).slice(0, 2).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(" · ")}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Compensation */}
      {pendingComps.length > 0 && (
        <div className="rounded-xl border border-amber-800/40 bg-amber-950/20 p-4">
          <div className="flex items-center gap-2 mb-3">
            <RotateCcw className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-semibold text-amber-300">Geri Alınabilir İşlemler</h2>
          </div>
          <div className="flex flex-col gap-2">
            {pendingComps.map(c => (
              <div key={c.exec_id} className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2">
                <span className="text-sm font-mono text-foreground">{c.tool}</span>
                <span className="text-xs text-muted-foreground">{c.compensate_fn}</span>
                <button
                  onClick={() => compMut.mutate(c.exec_id)}
                  disabled={compMut.isPending}
                  className="ml-auto text-xs rounded-md border border-amber-700 bg-amber-950 text-amber-400 hover:bg-amber-900 px-2 py-1 transition-colors"
                >
                  {compMut.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : "Geri Al"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
