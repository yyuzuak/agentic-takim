"use client";
import { fmtTime } from "../../lib/utils";
import type { ContextEvent, ToolInvocation } from "../../lib/api";
import { CheckCircle, Clock, AlertCircle, Info } from "lucide-react";
import { cn } from "../../lib/utils";

type TimelineItem = {
  time: string;
  label: string;
  detail?: string;
  kind: "success" | "pending" | "error" | "info";
};

function buildTimeline(events: ContextEvent[], tools: ToolInvocation[], taskCreatedAt: string | null): TimelineItem[] {
  const items: TimelineItem[] = [];

  if (taskCreatedAt) {
    items.push({ time: fmtTime(taskCreatedAt), label: "Görev alındı", kind: "info" });
  }

  // Events
  events.forEach(e => {
    const type = e.event_type;
    const p = e.payload ?? {};
    let label = type;
    let detail: string | undefined;
    let kind: TimelineItem["kind"] = "info";

    if (type === "plan_generated") {
      label = `Planlayıcı → ${(p.nodes as unknown[])?.length ?? "?"} düğüm DAG`;
      kind = "success";
    } else if (type === "node_started") {
      label = `${p.node_key} başladı`;
      kind = "pending";
    } else if (type === "node_completed") {
      label = `✓ ${p.node_key} tamamlandı`;
      kind = "success";
    } else if (type === "node_failed") {
      label = `${p.node_key} başarısız`;
      detail = String(p.error ?? "");
      kind = "error";
    } else if (type === "approval_requested") {
      label = `Onay bekleniyor → ${p.node_key}`;
      kind = "pending";
    } else if (type === "approval_granted") {
      label = `${p.actor ?? "Kullanıcı"} onayladı`;
      kind = "success";
    } else if (type === "approval_rejected") {
      label = `Reddedildi`;
      kind = "error";
    } else if (type === "tool_result") {
      const tool = (p as Record<string, unknown>).tool as string;
      label = `✓ ${tool} sonucu alındı`;
      kind = "success";
    }

    items.push({ time: fmtTime(e.created_at), label, detail, kind });
  });

  // Tool details not in events
  tools.forEach(t => {
    if (t.status === "success") {
      const detail = t.result ? Object.entries(t.result).slice(0, 2).map(([k, v]) => `${k}: ${v}`).join(", ") : undefined;
      // deduplicate with event entries — only add if no event for this tool
      const already = items.some(i => i.label.includes(t.tool) && i.kind === "success");
      if (!already) {
        items.push({ time: "—", label: `✓ ${t.tool}`, detail, kind: "success" });
      }
    } else if (t.status === "failed") {
      items.push({ time: "—", label: `✗ ${t.tool} hata`, detail: t.error_code ?? undefined, kind: "error" });
    }
  });

  return items;
}

const ICONS = {
  success: CheckCircle,
  pending: Clock,
  error: AlertCircle,
  info: Info,
};

const ICON_COLORS = {
  success: "text-success",
  pending: "text-warning",
  error: "text-destructive",
  info: "text-info",
};

export function Timeline({
  events,
  tools,
  taskCreatedAt,
}: {
  events: ContextEvent[];
  tools: ToolInvocation[];
  taskCreatedAt: string | null;
}) {
  const items = buildTimeline(events, tools, taskCreatedAt);

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground py-4">Henüz etkinlik yok.</p>;
  }

  return (
    <div className="flex flex-col">
      {items.map((item, i) => {
        const Icon = ICONS[item.kind];
        return (
          <div key={i} className="flex gap-3 group">
            <div className="flex flex-col items-center">
              <Icon className={cn("w-4 h-4 mt-0.5 shrink-0", ICON_COLORS[item.kind])} />
              {i < items.length - 1 && <div className="w-px flex-1 bg-border mt-1" />}
            </div>
            <div className="pb-4 min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="text-sm text-foreground">{item.label}</span>
                <span className="text-xs text-muted-foreground shrink-0">{item.time}</span>
              </div>
              {item.detail && (
                <p className="text-xs text-muted-foreground mt-0.5 truncate">{item.detail}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
