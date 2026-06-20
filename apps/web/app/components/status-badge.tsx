import {
  CheckCircle2, Loader2, Clock, XCircle, ShieldQuestion, Ban, AlertTriangle, type LucideIcon,
} from "lucide-react";
import { Badge, type BadgeProps } from "./ui/badge";
import { cn } from "../lib/utils";

type Variant = NonNullable<BadgeProps["variant"]>;
type Spec = { label: string; variant: Variant; icon: LucideIcon; spin?: boolean; pulse?: boolean };

const MAP: Record<string, Spec> = {
  done: { label: "Tamamlandı", variant: "success", icon: CheckCircle2 },
  applied: { label: "Uygulandı", variant: "success", icon: CheckCircle2 },
  healthy: { label: "Sağlıklı", variant: "success", icon: CheckCircle2 },
  running: { label: "Çalışıyor", variant: "info", icon: Loader2, spin: true },
  in_progress: { label: "Çalışıyor", variant: "info", icon: Loader2, spin: true },
  pending: { label: "Bekliyor", variant: "neutral", icon: Clock },
  ready: { label: "Hazır", variant: "neutral", icon: Clock },
  failed: { label: "Hatalı", variant: "danger", icon: XCircle },
  down: { label: "Çevrimdışı", variant: "danger", icon: XCircle },
  awaiting_approval: { label: "Onay Bekliyor", variant: "warning", icon: ShieldQuestion, pulse: true },
  blocked: { label: "Engellendi", variant: "warning", icon: Ban },
  degraded: { label: "Düşük", variant: "warning", icon: AlertTriangle },
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const s = MAP[status] ?? { label: status, variant: "neutral" as Variant, icon: Clock };
  const Icon = s.icon;
  return (
    <Badge variant={s.variant} className={cn(s.pulse && "animate-pulse", className)}>
      <Icon className={cn("w-3 h-3", s.spin && "animate-spin")} />
      {s.label}
    </Badge>
  );
}
