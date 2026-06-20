"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { motion } from "framer-motion";
import { getTasks, createTask, type TaskSummary } from "./lib/api";
import { StatusBadge } from "./components/status-badge";
import { Card } from "./components/ui/card";
import { Button } from "./components/ui/button";
import { Skeleton } from "./components/ui/skeleton";
import { timeAgo } from "./lib/utils";
import { Zap, ChevronRight, CircleDot } from "lucide-react";

function GoalInput() {
  const [goal, setGoal] = useState("");
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: (g: string) => createTask({ goal: g, actor: "studio" }),
    onSuccess: () => { setGoal(""); qc.invalidateQueries({ queryKey: ["tasks"] }); },
  });

  return (
    <Card className="relative overflow-hidden p-6 mb-8">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/[0.07] via-transparent to-transparent pointer-events-none" />
      <div className="relative">
        <h1 className="text-xl font-semibold tracking-tight mb-1">Yeni Görev</h1>
        <p className="text-sm text-muted-foreground mb-4">
          Hedefi yazın — sistem DAG oluşturur, ajanlar çalışır.
        </p>
        <div className="flex gap-2">
          <input
            value={goal}
            onChange={e => setGoal(e.target.value)}
            onKeyDown={e => e.key === "Enter" && goal.trim() && mut.mutate(goal.trim())}
            placeholder="ABC Makina'ya teklif hazırla…"
            className="flex-1 rounded-lg border border-border bg-background px-4 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
          />
          <Button onClick={() => goal.trim() && mut.mutate(goal.trim())} disabled={!goal.trim()} loading={mut.isPending}>
            {!mut.isPending && <Zap className="w-4 h-4" />}
            Çalıştır
          </Button>
        </div>
        {mut.isSuccess && (
          <p className="mt-2 text-xs text-success">
            Görev oluşturuldu →{" "}
            <Link href={`/tasks/${mut.data.task_id}`} className="underline">detay</Link>
          </p>
        )}
        {mut.isError && <p className="mt-2 text-xs text-destructive">{String(mut.error)}</p>}
      </div>
    </Card>
  );
}

function TaskCard({ task, index }: { task: TaskSummary; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(index * 0.03, 0.3) }}
    >
      <Link href={`/tasks/${task.id}`} className="block group">
        <Card hover className="p-4">
          <div className="flex items-start justify-between gap-2 mb-2">
            <StatusBadge status={task.status} />
            <span className="text-xs text-muted-foreground shrink-0">{timeAgo(task.created_at)}</span>
          </div>
          <p className="text-sm font-medium line-clamp-2 mb-1">{task.goal}</p>
          {task.skill && <p className="text-xs text-muted-foreground">{task.skill}</p>}
          <div className="mt-3 flex items-center text-xs text-primary opacity-0 group-hover:opacity-100 transition-opacity">
            Detay <ChevronRight className="w-3 h-3 ml-0.5" />
          </div>
        </Card>
      </Link>
    </motion.div>
  );
}

const COLS: { label: string; statuses: string[] }[] = [
  { label: "Aktif", statuses: ["running", "in_progress", "pending", "ready", "awaiting_approval", "blocked"] },
  { label: "Tamamlanan", statuses: ["done"] },
  { label: "Hatalı", statuses: ["failed"] },
];

export default function StudioPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["tasks"],
    queryFn: () => getTasks(100),
    refetchInterval: 4000,
  });
  const tasks = data?.tasks ?? [];

  return (
    <div>
      <GoalInput />

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[0, 1, 2].map(c => (
            <div key={c} className="space-y-2">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ))}
        </div>
      )}

      {!isLoading && tasks.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <CircleDot className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p className="text-sm">Henüz görev yok. Yukarıdan bir hedef girin.</p>
        </div>
      )}

      {tasks.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {COLS.map(({ label, statuses }) => {
            const col = tasks.filter(t => statuses.includes(t.status));
            return (
              <div key={label}>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{label}</span>
                  <span className="text-xs bg-muted text-muted-foreground rounded-full px-2 py-0.5 tabular-nums">{col.length}</span>
                </div>
                <div className="flex flex-col gap-2">
                  {col.length === 0 && (
                    <div className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground text-center">Boş</div>
                  )}
                  {col.map((t, i) => <TaskCard key={t.id} task={t} index={i} />)}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
