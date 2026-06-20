"use client";
import { useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getTask, getTaskTools, getTaskCompensations, getTaskEvents, getTaskArtifacts,
  approveNode, approveTask, applyCompensation,
  type NodeDetail, type PlanNode,
} from "../../lib/api";
import { ArtifactsPanel } from "./_artifacts";
import { BuildsPanel } from "./_builds";
import { StatusBadge } from "../../components/status-badge";
import { Card } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Skeleton } from "../../components/ui/skeleton";
import { DagView } from "./_dag";
import { Timeline } from "./_timeline";
import { timeAgo } from "../../lib/utils";
import { RotateCcw, CheckCheck } from "lucide-react";

export default function TaskDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const qc = useQueryClient();
  const refetch = () => qc.invalidateQueries({ queryKey: ["task", id] });

  const { data: task, isLoading } = useQuery({
    queryKey: ["task", id], queryFn: () => getTask(id), refetchInterval: 2000,
  });
  const { data: toolData } = useQuery({
    queryKey: ["task-tools", id], queryFn: () => getTaskTools(id), refetchInterval: 2000,
  });
  const { data: compData } = useQuery({
    queryKey: ["task-compensations", id], queryFn: () => getTaskCompensations(id), refetchInterval: 4000,
  });
  const { data: evData } = useQuery({
    queryKey: ["task-events", id], queryFn: () => getTaskEvents(id), refetchInterval: 2000,
  });
  const { data: artifactData } = useQuery({
    queryKey: ["task-artifacts", id], queryFn: () => getTaskArtifacts(id), refetchInterval: 2000,
  });

  const approveMut = useMutation({ mutationFn: (key: string) => approveNode(id, key), onSuccess: refetch });
  const approveTaskMut = useMutation({ mutationFn: () => approveTask(id), onSuccess: refetch });
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

  if (isLoading) return <Skeleton className="h-96 w-full" />;
  if (!task) return <p className="text-muted-foreground">Görev bulunamadı.</p>;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <Card className="p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <h1 className="text-base font-semibold mb-1 leading-snug">{task.goal}</h1>
            <div className="flex items-center gap-3 flex-wrap">
              <StatusBadge status={task.status} />
              <span className="text-xs text-muted-foreground">{timeAgo(task.created_at)}</span>
              <span className="text-xs text-muted-foreground font-mono">{task.id.slice(0, 8)}</span>
            </div>
          </div>
          {needsApproval && (
            <Button variant="primary" onClick={() => approveTaskMut.mutate()} loading={approveTaskMut.isPending}>
              {!approveTaskMut.isPending && <CheckCheck className="w-4 h-4" />}
              Onayla
            </Button>
          )}
        </div>
      </Card>

      {/* DAG + Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-4 flex flex-col gap-3">
          <h2 className="text-sm font-semibold">Yürütme Planı</h2>
          {/* API `nodes` döndürür (plan değil); DagView'in ihtiyacı olan key/depends_on/skill/tool/kind nodes'ta var */}
          {(task.nodes?.length ?? 0) > 0 ? (
            <div style={{ height: 400 }}>
              <DagView plan={(task.nodes ?? []) as unknown as PlanNode[]} nodeMap={nodeMap} onApproveNode={(key) => approveMut.mutate(key)} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Plan henüz oluşturulmadı.</p>
          )}
        </Card>

        <Card className="p-4 flex flex-col gap-3">
          <h2 className="text-sm font-semibold">Canlı İlerleme</h2>
          <div className="overflow-y-auto max-h-[400px] pr-1">
            <Timeline events={evData?.events ?? []} tools={toolData?.invocations ?? []} taskCreatedAt={task.created_at} />
          </div>
        </Card>
      </div>

      {/* Artifacts — ajanların ürettiği gerçek çıktılar (v2.0-A) */}
      {(artifactData?.count ?? 0) > 0 && <ArtifactsPanel artifacts={artifactData!.artifacts} taskId={id} />}

      {/* v2.1 Workspace Runtime — artifact'ları doğrulanmış repo'ya çevir + Build Explorer */}
      {(artifactData?.artifacts.some(a => (a.content as { files?: unknown } | null)?.files)) && (
        <BuildsPanel taskId={id} />
      )}

      {/* Tool Invocations */}
      {(toolData?.count ?? 0) > 0 && (
        <Card className="p-4">
          <h2 className="text-sm font-semibold mb-3">Tool Çağrıları ({toolData!.count})</h2>
          <div className="flex flex-col gap-2">
            {toolData!.invocations.map((inv, i) => (
              <div key={i} className="rounded-lg border border-border bg-muted/30 px-3 py-2 flex items-center gap-3 flex-wrap">
                <StatusBadge status={inv.status} className="shrink-0" />
                <span className="text-sm font-mono">{inv.tool}</span>
                <span className="text-xs text-muted-foreground">{inv.node_key}</span>
                {inv.dry_run && <Badge variant="info">dry-run</Badge>}
                {inv.rate_limited && <Badge variant="warning">rate-limited</Badge>}
                {inv.result && (
                  <span className="text-xs text-muted-foreground ml-auto hidden lg:block truncate max-w-xs">
                    {Object.entries(inv.result).slice(0, 2).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(" · ")}
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Compensation */}
      {pendingComps.length > 0 && (
        <Card className="p-4 border-warning/30 bg-warning/[0.06]">
          <div className="flex items-center gap-2 mb-3">
            <RotateCcw className="w-4 h-4 text-warning" />
            <h2 className="text-sm font-semibold text-warning">Geri Alınabilir İşlemler</h2>
          </div>
          <div className="flex flex-col gap-2">
            {pendingComps.map(c => (
              <div key={c.exec_id} className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2">
                <span className="text-sm font-mono">{c.tool}</span>
                <span className="text-xs text-muted-foreground">{c.compensate_fn}</span>
                <Button
                  variant="outline" size="sm" className="ml-auto"
                  onClick={() => compMut.mutate(c.exec_id)} loading={compMut.isPending}
                >
                  Geri Al
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
