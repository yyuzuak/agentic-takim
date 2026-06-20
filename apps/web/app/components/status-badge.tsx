import { cn } from "../lib/utils";

const MAP: Record<string, { label: string; cls: string; dot: string }> = {
  done:               { label: "Tamamlandı",     cls: "bg-emerald-950 text-emerald-400 border-emerald-800",  dot: "bg-emerald-400" },
  running:            { label: "Çalışıyor",       cls: "bg-blue-950 text-blue-400 border-blue-800",          dot: "bg-blue-400 animate-pulse" },
  in_progress:        { label: "Çalışıyor",       cls: "bg-blue-950 text-blue-400 border-blue-800",          dot: "bg-blue-400 animate-pulse" },
  pending:            { label: "Bekliyor",         cls: "bg-zinc-900 text-zinc-400 border-zinc-700",          dot: "bg-zinc-500" },
  ready:              { label: "Hazır",            cls: "bg-zinc-900 text-zinc-400 border-zinc-700",          dot: "bg-zinc-400" },
  failed:             { label: "Hatalı",           cls: "bg-red-950 text-red-400 border-red-800",             dot: "bg-red-400" },
  awaiting_approval:  { label: "Onay Bekliyor",   cls: "bg-amber-950 text-amber-400 border-amber-800",       dot: "bg-amber-400 animate-pulse" },
  blocked:            { label: "Engellendi",       cls: "bg-orange-950 text-orange-400 border-orange-800",    dot: "bg-orange-400" },
  applied:            { label: "Uygulandı",        cls: "bg-emerald-950 text-emerald-400 border-emerald-800", dot: "bg-emerald-400" },
  healthy:            { label: "Sağlıklı",         cls: "bg-emerald-950 text-emerald-400 border-emerald-800", dot: "bg-emerald-400" },
  degraded:           { label: "Düşük",            cls: "bg-amber-950 text-amber-400 border-amber-800",       dot: "bg-amber-400" },
  down:               { label: "Çevrimdışı",       cls: "bg-red-950 text-red-400 border-red-800",             dot: "bg-red-400" },
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const m = MAP[status] ?? { label: status, cls: "bg-zinc-900 text-zinc-400 border-zinc-700", dot: "bg-zinc-500" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-xs font-medium", m.cls, className)}>
      <span className={cn("w-1.5 h-1.5 rounded-full", m.dot)} />
      {m.label}
    </span>
  );
}
