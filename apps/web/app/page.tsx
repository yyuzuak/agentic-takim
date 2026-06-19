"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { StatusBadge, card } from "./ui";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:8000";

export default function Home() {
  const router = useRouter();
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [recent, setRecent] = useState<{ id: string; goal: string; status: string; created_at: string }[]>([]);
  const [goal, setGoal] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetch(`${API}/health`).then(r => r.json()).then(setHealth).catch(() => {});
    fetch(`${API}/tasks?limit=5`).then(r => r.json()).then(d => setRecent(d.tasks ?? [])).catch(() => {});
  }, []);

  async function createTask() {
    if (!goal.trim()) return;
    setSubmitting(true);
    try {
      const r = await fetch(`${API}/tasks`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      const d = await r.json();
      router.push(`/tasks/${d.task_id}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: "1.6rem", fontWeight: 700, marginBottom: "0.25rem" }}>Kontrol Merkezi</h1>
      <p style={{ color: "#8b98b8", marginBottom: "2rem", fontSize: "0.9rem" }}>
        {health ? (health.status === "ok" ? "✓ Control-plane bağlı" : "✗ Bağlantı hatası") : "Bağlanıyor…"}
        {health && <span style={{ marginLeft: 12, opacity: 0.6 }}>{Object.entries((health.features as Record<string, boolean>) ?? {}).filter(([, v]) => v).map(([k]) => k).join(" · ") || "temel mod"}</span>}
      </p>

      {/* Hızlı görev oluştur */}
      <div style={card}>
        <h2 style={{ fontSize: "1rem", marginBottom: "0.75rem", fontWeight: 600 }}>Yeni Görev</h2>
        <textarea
          value={goal}
          onChange={e => setGoal(e.target.value)}
          placeholder="Hedef girin… (ör: ABC Makina HTD 8M teklifi hazırla, stok kontrol, PDF, WhatsApp)"
          style={{ width: "100%", minHeight: 72, background: "#0b0e14", border: "1px solid #1e2535", borderRadius: 6, color: "#e6e6e6", padding: "0.6rem", fontSize: "0.9rem", resize: "vertical", boxSizing: "border-box" }}
          onKeyDown={e => { if (e.key === "Enter" && e.metaKey) createTask(); }}
        />
        <button
          onClick={createTask}
          disabled={submitting || !goal.trim()}
          style={{ marginTop: "0.6rem", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, padding: "0.5rem 1.2rem", cursor: "pointer", fontSize: "0.9rem", opacity: submitting ? 0.6 : 1 }}
        >
          {submitting ? "Gönderiliyor…" : "Görevi Başlat →"}
        </button>
      </div>

      {/* Son görevler */}
      {recent.length > 0 && (
        <div style={{ marginTop: "1.5rem" }}>
          <h2 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.75rem" }}>Son Görevler</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {recent.map(t => (
              <a key={t.id} href={`/tasks/${t.id}`} style={{ ...card, display: "flex", alignItems: "center", gap: "0.75rem", textDecoration: "none", color: "#e6e6e6" }}>
                <StatusBadge status={t.status} />
                <span style={{ flex: 1, fontSize: "0.9rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.goal}</span>
                <span style={{ fontSize: "0.78rem", color: "#8b98b8", whiteSpace: "nowrap" }}>{t.created_at ? new Date(t.created_at).toLocaleString("tr-TR") : ""}</span>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
