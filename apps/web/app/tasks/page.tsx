"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { getTasks } from "../lib/api";
import { StatusBadge } from "../components/status-badge";
import { timeAgo } from "../lib/utils";
import { Loader2, ChevronRight } from "lucide-react";

export default function TasksPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["tasks"],
    queryFn: () => getTasks(100),
    refetchInterval: 4000,
  });

  const tasks = data?.tasks ?? [];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Görevler</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{tasks.length} görev · 4s polling</p>
        </div>
        <Link
          href="/"
          className="inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          Yeni Görev
        </Link>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Yükleniyor…
        </div>
      )}

      <div className="flex flex-col gap-2">
        {tasks.map(t => (
          <Link key={t.id} href={`/tasks/${t.id}`} className="group block">
            <div className="rounded-lg border border-border bg-card px-4 py-3 flex items-center gap-4 hover:border-primary/40 hover:bg-muted/20 transition-all">
              <StatusBadge status={t.status} className="shrink-0" />
              <p className="flex-1 text-sm text-foreground truncate">{t.goal}</p>
              <span className="text-xs text-muted-foreground shrink-0 hidden sm:block">{t.skill ?? "—"}</span>
              <span className="text-xs text-muted-foreground shrink-0">{timeAgo(t.created_at)}</span>
              <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
