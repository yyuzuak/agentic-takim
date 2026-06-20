"use client";
import { useQuery } from "@tanstack/react-query";
import { getMetrics } from "../lib/api";
import { Eye, BarChart3, ShieldCheck, Zap } from "lucide-react";

function MetricCard({ label, value, desc, icon: Icon }: {
  label: string; value: string | number; desc?: string; icon: React.ElementType;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground font-medium">{label}</span>
        <Icon className="w-4 h-4 text-muted-foreground" />
      </div>
      <p className="text-2xl font-bold text-foreground">{value}</p>
      {desc && <p className="text-xs text-muted-foreground mt-1">{desc}</p>}
    </div>
  );
}

export default function ObserverPage() {
  const { data: metrics } = useQuery({
    queryKey: ["metrics"],
    queryFn: getMetrics,
    refetchInterval: 5000,
  });

  const m = metrics ?? {};
  const tasks_total = (m.tasks_completed ?? 0) + (m.tasks_failed ?? 0) + (m.tasks_pending ?? 0);
  const successRate = tasks_total > 0
    ? Math.round(((m.tasks_completed ?? 0) / tasks_total) * 100)
    : 0;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Eye className="w-5 h-5 text-muted-foreground" />
          Observer Dashboard
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Sistem geneli izleme · v1.3'te Gözcü agent gerçek veriyle doldurur
        </p>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <MetricCard
          label="Toplam Görev"
          value={tasks_total}
          desc={`${m.tasks_completed ?? 0} tamamlandı`}
          icon={BarChart3}
        />
        <MetricCard
          label="Başarı Oranı"
          value={`${successRate}%`}
          desc={`${m.tasks_failed ?? 0} hatalı`}
          icon={ShieldCheck}
        />
        <MetricCard
          label="Tool Çağrısı"
          value={m.tools_total ?? 0}
          desc={`${m.tools_failed ?? 0} başarısız`}
          icon={Zap}
        />
        <MetricCard
          label="Yeniden Deneme"
          value={m.retries_total ?? 0}
          desc={`${m.dlq_total ?? 0} DLQ`}
          icon={BarChart3}
        />
      </div>

      {/* Coming soon callout */}
      <div className="rounded-xl border border-dashed border-border bg-muted/10 p-8 text-center">
        <Eye className="w-12 h-12 text-muted-foreground/30 mx-auto mb-3" />
        <p className="text-sm font-medium text-muted-foreground">Gözcü Agent — v1.3</p>
        <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
          Kalite skorlama, anomali tespiti ve öğrenme döngüsü burada görüntülenecek.
          Şu an mevcut metrikler tool-runtime'dan akıyor.
        </p>
      </div>
    </div>
  );
}
