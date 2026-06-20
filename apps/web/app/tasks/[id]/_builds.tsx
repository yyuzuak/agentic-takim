"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Hammer, FileCode, CheckCircle2, XCircle, ChevronRight, ChevronDown } from "lucide-react";
import { buildRepo, getTaskBuilds, getBuild, getBuildFile, type BuildRecord } from "../../lib/api";
import { Card } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { cn } from "../../lib/utils";

function FileViewer({ buildId, path }: { buildId: string; path: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["build-file", buildId, path],
    queryFn: () => getBuildFile(buildId, path),
  });
  return (
    <pre className="text-xs p-3 overflow-x-auto bg-background/60 leading-relaxed max-h-80">
      <code>{isLoading ? "yükleniyor…" : data?.content}</code>
    </pre>
  );
}

function BuildCard({ build }: { build: BuildRecord }) {
  const [open, setOpen] = useState(false);
  const [openFile, setOpenFile] = useState<string | null>(null);
  const { data: detail } = useQuery({
    queryKey: ["build", build.build_id],
    queryFn: () => getBuild(build.build_id),
    enabled: open,
  });

  const passed = build.status === "validated";
  const vr = build.validator_result;

  return (
    <Card className="p-4">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center gap-3 text-left">
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <span className="text-sm font-semibold">Build #{build.build_number}</span>
        <Badge variant={passed ? "success" : "danger"}>
          {passed ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
          {passed ? "Validator Passed" : "Validator Failed"} (v{build.validator_version})
        </Badge>
        <span className="ml-auto text-xs text-muted-foreground font-mono">
          {build.build_fingerprint} · {build.file_count} dosya
        </span>
      </button>

      {open && (
        <div className="mt-4 space-y-3">
          {/* validator rapor */}
          {vr && vr.issues.length > 0 && (
            <div className="text-xs space-y-0.5">
              {vr.issues.map((i, k) => (
                <div key={k} className={cn(i.level === "hard" ? "text-destructive" : "text-warning")}>
                  {i.level === "hard" ? "✗" : "·"} [{i.cat}] {i.file}: {i.msg}
                </div>
              ))}
            </div>
          )}
          {vr && vr.hard === 0 && (
            <div className="text-xs text-success space-y-0.5">
              <div>✓ Dependency Resolution</div>
              <div>✓ Import Graph</div>
              <div>✓ Prisma Schema Valid (id/relation)</div>
              <div>✓ Route → Model · Fetch → Endpoint</div>
            </div>
          )}

          {/* dosya ağacı (manifest) */}
          <div>
            <p className="text-xs font-semibold text-muted-foreground mb-1">
              Files ({detail?.files.length ?? "…"})
            </p>
            <div className="rounded-lg border border-border divide-y divide-border">
              {detail?.files.map(f => (
                <div key={f.path}>
                  <button
                    onClick={() => setOpenFile(openFile === f.path ? null : f.path)}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-xs font-mono hover:bg-muted/40 transition-colors"
                  >
                    <FileCode className="w-3.5 h-3.5 text-info shrink-0" />
                    <span className="truncate">{f.path}</span>
                    <span className="ml-auto text-muted-foreground shrink-0">{f.size}b</span>
                  </button>
                  {openFile === f.path && <FileViewer buildId={build.build_id} path={f.path} />}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg bg-muted/40 p-2 text-xs font-mono text-muted-foreground">
            cd workspace && npm install && npx prisma db push && npm run dev
          </div>
        </div>
      )}
    </Card>
  );
}

export function BuildsPanel({ taskId }: { taskId: string }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["task-builds", taskId],
    queryFn: () => getTaskBuilds(taskId),
    refetchInterval: 5000,
  });
  const mut = useMutation({
    mutationFn: () => buildRepo(taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task-builds", taskId] }),
  });

  const builds = data?.builds ?? [];

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold">Workspace · Build'ler ({builds.length})</h2>
        <Button size="sm" onClick={() => mut.mutate()} loading={mut.isPending}>
          {!mut.isPending && <Hammer className="w-4 h-4" />}
          Repo Üret
        </Button>
      </div>
      {mut.isError && <p className="text-xs text-destructive mb-2">{String(mut.error)}</p>}
      {builds.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Henüz build yok. "Repo Üret" ile artifact'ları doğrulanmış repo'ya çevir.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {builds.map(b => <BuildCard key={b.build_id} build={b} />)}
        </div>
      )}
    </Card>
  );
}
