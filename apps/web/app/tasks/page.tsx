"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { StatusBadge, card, Section } from "../ui";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:8000";

type Task = { id: string; goal: string; status: string; skill: string | null; created_at: string };

export default function TasksPage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [goal, setGoal] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    fetch(`${API}/tasks?limit=100`).then(r => r.json()).then(d => setTasks(d.tasks ?? [])).catch(() => {});
  };

  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, []);

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
    } finally { setSubmitting(false); }
  }

  return (
    <div>
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "1.5rem" }}>Görevler</h1>

      <div style={card}>
        <textarea
          value={goal}
          onChange={e => setGoal(e.target.value)}
          placeholder="Yeni görev hedefi…"
          style={{ width: "100%", minHeight: 60, background: "#0b0e14", border: "1px solid #1e2535", borderRadius: 6, color: "#e6e6e6", padding: "0.6rem", fontSize: "0.9rem", resize: "vertical", boxSizing: "border-box" }}
          onKeyDown={e => { if (e.key === "Enter" && e.metaKey) createTask(); }}
        />
        <button onClick={createTask} disabled={submitting || !goal.trim()}
          style={{ marginTop: "0.5rem", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, padding: "0.45rem 1rem", cursor: "pointer", fontSize: "0.85rem" }}>
          {submitting ? "Gönderiliyor…" : "Başlat →"}
        </button>
      </div>

      <Section title={`${tasks.length} görev`}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {tasks.map(t => (
            <a key={t.id} href={`/tasks/${t.id}`}
              style={{ ...card, display: "flex", alignItems: "center", gap: "0.75rem", textDecoration: "none", color: "#e6e6e6", padding: "0.75rem 1rem" }}>
              <StatusBadge status={t.status} />
              <span style={{ flex: 1, fontSize: "0.88rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.goal}</span>
              <span style={{ fontSize: "0.75rem", color: "#8b98b8", whiteSpace: "nowrap" }}>
                {t.skill && <span style={{ marginRight: 8, background: "#1e2535", borderRadius: 4, padding: "1px 6px" }}>{t.skill}</span>}
                {t.created_at ? new Date(t.created_at).toLocaleString("tr-TR") : ""}
              </span>
            </a>
          ))}
          {tasks.length === 0 && <p style={{ color: "#8b98b8", fontSize: "0.9rem" }}>Henüz görev yok.</p>}
        </div>
      </Section>
    </div>
  );
}
