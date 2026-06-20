"use client";
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getMemory, recallMemory } from "../lib/api";
import { Search, Brain, Loader2 } from "lucide-react";

export default function MemoryPage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");

  const { data: list, isLoading } = useQuery({
    queryKey: ["memory"],
    queryFn: getMemory,
    refetchInterval: 10000,
  });

  const recall = useMutation({
    mutationFn: (q: string) => recallMemory(q),
  });

  function handleRecall() {
    if (!query.trim()) return;
    setSubmitted(query.trim());
    recall.mutate(query.trim());
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Hafıza Gezgini</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Semantik bellek deposu — {list?.count ?? "…"} kayıt</p>
      </div>

      {/* Recall input */}
      <div className="rounded-xl border border-border bg-card p-5 mb-6">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground" />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleRecall()}
              placeholder="Geçmiş görevleri sorgula…"
              className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-border bg-muted text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
          <button
            onClick={handleRecall}
            disabled={!query.trim() || recall.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-50 hover:bg-primary/90 transition-colors"
          >
            {recall.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
            Sorgula
          </button>
        </div>

        {recall.isSuccess && recall.data && (
          <div className="mt-4 p-4 rounded-lg bg-muted border border-border">
            <p className="text-xs text-muted-foreground mb-2">
              "{submitted}" için {recall.data.results?.length ?? 0} sonuç:
            </p>
            <div className="flex flex-col gap-2">
              {recall.data.results?.map((r, i) => (
                <div key={i} className="flex items-start gap-3">
                  <span className="text-xs bg-primary/20 text-primary rounded px-1.5 py-0.5 shrink-0">
                    {r.score ? r.score.toFixed(2) : "—"}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm text-foreground truncate">{r.goal ?? r.content ?? "—"}</p>
                    {r.skill && <p className="text-xs text-muted-foreground">{r.skill}</p>}
                  </div>
                </div>
              ))}
              {!recall.data.results?.length && (
                <p className="text-sm text-muted-foreground">Sonuç bulunamadı.</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Full memory table */}
      {isLoading && <p className="text-sm text-muted-foreground">Yükleniyor…</p>}
      {list && list.entries.length > 0 && (
        <div className="rounded-xl border border-border overflow-hidden">
          <div className="px-4 py-3 border-b border-border bg-muted/30">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Tüm Kayıtlar</span>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left px-4 py-2.5 text-xs text-muted-foreground font-semibold">Hedef</th>
                <th className="text-left px-4 py-2.5 text-xs text-muted-foreground font-semibold">Skill</th>
                <th className="text-right px-4 py-2.5 text-xs text-muted-foreground font-semibold">Başarı</th>
                <th className="text-right px-4 py-2.5 text-xs text-muted-foreground font-semibold">Tekrar</th>
              </tr>
            </thead>
            <tbody>
              {list.entries.map((e, i) => (
                <tr key={i} className="border-b border-border last:border-0 hover:bg-muted/20">
                  <td className="px-4 py-2.5 text-foreground truncate max-w-xs">{e.goal}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{e.skill ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right">
                    <span className={e.success ? "text-emerald-400" : "text-red-400"}>
                      {e.success ? "✓" : "✗"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-muted-foreground">{e.reuse_success_count ?? 0}x</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
