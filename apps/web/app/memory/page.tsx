"use client";
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Search, Brain, CheckCircle2, XCircle } from "lucide-react";
import { getMemory, recallMemory } from "../lib/api";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Table, THead, TBody, TR, TH, TD } from "../components/ui/table";
import { Skeleton } from "../components/ui/skeleton";

export default function MemoryPage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");

  const { data: list, isLoading } = useQuery({
    queryKey: ["memory"], queryFn: getMemory, refetchInterval: 10000,
  });
  const recall = useMutation({ mutationFn: (q: string) => recallMemory(q) });

  function handleRecall() {
    if (!query.trim()) return;
    setSubmitted(query.trim());
    recall.mutate(query.trim());
  }

  const hits = recall.data?.hits ?? [];

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Hafıza Gezgini</h1>
        <p className="text-sm text-muted-foreground mt-0.5 tabular-nums">
          Semantik bellek deposu — {list?.count ?? "…"} kayıt
        </p>
      </div>

      {/* Recall hero */}
      <Card className="relative overflow-hidden p-5 mb-6">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/[0.06] to-transparent pointer-events-none" />
        <div className="relative">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleRecall()}
                placeholder="Geçmiş görevleri sorgula…"
                className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-border bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
            <Button onClick={handleRecall} disabled={!query.trim()} loading={recall.isPending}>
              {!recall.isPending && <Brain className="w-4 h-4" />}
              Sorgula
            </Button>
          </div>

          {recall.isSuccess && (
            <div className="mt-4 p-4 rounded-lg bg-muted/50 border border-border">
              <p className="text-xs text-muted-foreground mb-2">
                "{submitted}" için {hits.length} sonuç
                {recall.data && hits.length > 0 && <span> · ort. skor {recall.data.avg_score} · güven {recall.data.confidence}</span>}:
              </p>
              <div className="flex flex-col gap-2">
                {hits.map((r, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <Badge variant="info" className="shrink-0 tabular-nums">
                      {typeof r.score === "number" ? r.score.toFixed(2) : "—"}
                    </Badge>
                    <div className="min-w-0">
                      <p className="text-sm truncate">{r.goal ?? "—"}</p>
                      {r.workflow_type && <p className="text-xs text-muted-foreground">{r.workflow_type}</p>}
                    </div>
                  </div>
                ))}
                {hits.length === 0 && <p className="text-sm text-muted-foreground">Sonuç bulunamadı.</p>}
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* Full table */}
      {isLoading && <Skeleton className="h-48 w-full" />}
      {list && list.entries.length > 0 && (
        <Table>
          <THead>
            <tr>
              <TH>Hedef</TH>
              <TH>Tip</TH>
              <TH className="text-right">Sonuç</TH>
              <TH className="text-right">Tekrar</TH>
            </tr>
          </THead>
          <TBody>
            {list.entries.map((e, i) => {
              const ok = e.outcome === "done";
              return (
                <TR key={i}>
                  <TD className="max-w-xs"><span className="block truncate">{e.goal}</span></TD>
                  <TD className="text-muted-foreground">{e.workflow_type ?? "—"}</TD>
                  <TD className="text-right">
                    {ok
                      ? <CheckCircle2 className="w-4 h-4 text-success inline" />
                      : <XCircle className="w-4 h-4 text-destructive inline" />}
                  </TD>
                  <TD className="text-right text-muted-foreground tabular-nums">{e.reuse_success_count ?? 0}x</TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      )}
    </div>
  );
}
