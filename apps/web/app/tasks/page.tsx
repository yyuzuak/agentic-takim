"use client";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getTasks } from "../lib/api";
import { StatusBadge } from "../components/status-badge";
import { Button } from "../components/ui/button";
import { Table, THead, TBody, TR, TH, TD } from "../components/ui/table";
import { Skeleton } from "../components/ui/skeleton";
import { timeAgo } from "../lib/utils";
import { ChevronRight } from "lucide-react";

export default function TasksPage() {
  const router = useRouter();
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
          <h1 className="text-xl font-semibold tracking-tight">Görevler</h1>
          <p className="text-sm text-muted-foreground mt-0.5 tabular-nums">{tasks.length} görev · 4s polling</p>
        </div>
        <Link href="/"><Button>Yeni Görev</Button></Link>
      </div>

      {isLoading && <Skeleton className="h-64 w-full" />}

      {!isLoading && (
        <Table>
          <THead>
            <tr>
              <TH>Durum</TH>
              <TH>Hedef</TH>
              <TH className="hidden sm:table-cell">Skill</TH>
              <TH className="text-right">Zaman</TH>
              <TH className="w-8" />
            </tr>
          </THead>
          <TBody>
            {tasks.map(t => (
              <TR key={t.id} className="cursor-pointer group" onClick={() => router.push(`/tasks/${t.id}`)}>
                <TD><StatusBadge status={t.status} /></TD>
                <TD className="max-w-md"><span className="block truncate">{t.goal}</span></TD>
                <TD className="hidden sm:table-cell text-muted-foreground">{t.skill ?? "—"}</TD>
                <TD className="text-right text-muted-foreground whitespace-nowrap">{timeAgo(t.created_at)}</TD>
                <TD><ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" /></TD>
              </TR>
            ))}
            {tasks.length === 0 && (
              <TR>
                <TD className="text-center text-muted-foreground py-8" colSpan={5}>Görev yok.</TD>
              </TR>
            )}
          </TBody>
        </Table>
      )}
    </div>
  );
}
