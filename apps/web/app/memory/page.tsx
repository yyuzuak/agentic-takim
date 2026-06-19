"use client";

import { useEffect, useState } from "react";
import { StatusBadge, card, Section } from "../ui";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:8000";

type MemoryEntry = {
  task_id: string; goal: string; workflow_type: string; outcome: string;
  status: string; provider: string; retrieval_count: number; reuse_success_count: number;
  refinement_summary: string | null; parent_memory_ids: string[] | null;
};

export default function MemoryPage() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [recallGoal, setRecallGoal] = useState("");
  const [recallResult, setRecallResult] = useState<unknown>(null);

  useEffect(() => {
    fetch(`${API}/memory`).then(r => r.json()).then(d => setEntries(d.entries ?? [])).catch(() => {});
  }, []);

  async function recall() {
    if (!recallGoal.trim()) return;
    const r = await fetch(`${API}/memory/recall?goal=${encodeURIComponent(recallGoal)}`).then(r => r.json()).catch(() => null);
    setRecallResult(r);
  }

  return (
    <div>
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "1.5rem" }}>Hafıza Tarayıcı</h1>

      <div style={card}>
        <h2 style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "0.6rem" }}>Hafıza Sorgula</h2>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            value={recallGoal}
            onChange={e => setRecallGoal(e.target.value)}
            placeholder="Hedef ile sorgula…"
            onKeyDown={e => { if (e.key === "Enter") recall(); }}
            style={{ flex: 1, background: "#0b0e14", border: "1px solid #1e2535", borderRadius: 6, color: "#e6e6e6", padding: "0.45rem 0.6rem", fontSize: "0.85rem" }}
          />
          <button onClick={recall}
            style={{ background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, padding: "0.45rem 0.9rem", cursor: "pointer", fontSize: "0.85rem" }}>
            Sorgula
          </button>
        </div>
        {recallResult && (
          <pre style={{ marginTop: "0.75rem", fontSize: "0.75rem", color: "#8b98b8", overflowX: "auto" }}>
            {JSON.stringify(recallResult, null, 2)}
          </pre>
        )}
      </div>

      <Section title={`${entries.length} hafıza kaydı`}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {entries.map((e, i) => (
            <div key={i} style={card}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
                <StatusBadge status={e.status} />
                <span style={{ fontSize: "0.75rem", background: "#1e2535", borderRadius: 4, padding: "1px 6px", color: "#8b98b8" }}>{e.workflow_type}</span>
                <span style={{ fontSize: "0.75rem", color: "#475569" }}>{e.provider}</span>
                <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "#475569" }}>
                  recall:{e.retrieval_count} reuse:{e.reuse_success_count}
                </span>
              </div>
              <div style={{ fontSize: "0.88rem", marginBottom: "0.25rem" }}>{e.goal}</div>
              {e.outcome && <div style={{ fontSize: "0.78rem", color: "#8b98b8" }}>{e.outcome}</div>}
              {e.refinement_summary && (
                <div style={{ marginTop: "0.4rem", fontSize: "0.75rem", color: "#475569", fontStyle: "italic" }}>
                  ↻ {e.refinement_summary}
                </div>
              )}
              <div style={{ marginTop: "0.35rem", fontSize: "0.72rem", color: "#334155" }}>{e.task_id}</div>
            </div>
          ))}
          {entries.length === 0 && <p style={{ color: "#8b98b8", fontSize: "0.9rem" }}>Henüz hafıza kaydı yok.</p>}
        </div>
      </Section>
    </div>
  );
}
