"use client";

import { useEffect, useState, useCallback } from "react";
import { StatusBadge, card, Section } from "../../ui";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:8000";

type Node = { key: string; agent: string; skill: string; kind: string; tool: string | null; role: string; status: string; result: unknown; retry_count: number; max_retries: number; error_code: string | null; depends_on: string[] };
type Task = { id: string; goal: string; status: string; result: unknown; error: string | null; nodes: Node[] };
type Event = { seq: number; type: string; agent: string; node_key: string; payload: Record<string, unknown> };
type ToolInv = { node_key: string; tool: string; status: string; attempt: number; error_code: string | null; result: unknown; dry_run: boolean; rate_limited: boolean };
type Compensation = { tool: string; compensate_fn: string | null; status: string; created_at: string };

const KIND_ICON: Record<string, string> = { tool: "🔧", approval: "✋", reasoning: "🧠" };

function DAGNode({ node, onApprove }: { node: Node; onApprove: (key: string) => void }) {
  const isApproval = node.kind === "approval";
  const needsApproval = isApproval && node.status === "awaiting_approval";
  const borderColor = needsApproval ? "#d97706" : node.status === "done" ? "#16a34a" : node.status === "failed" ? "#dc2626" : node.status === "running" ? "#2563eb" : "#1e2535";

  return (
    <div style={{ border: `1.5px solid ${borderColor}`, borderRadius: 8, padding: "0.6rem 0.75rem", minWidth: 140, background: "#0d1117", flex: "0 0 auto" }}>
      <div style={{ fontSize: "0.7rem", color: "#8b98b8", marginBottom: 3 }}>
        {KIND_ICON[node.kind] ?? "•"} {node.key}
      </div>
      <div style={{ fontSize: "0.82rem", fontWeight: 600, marginBottom: 4 }}>
        {node.tool ?? node.skill ?? node.agent ?? "—"}
      </div>
      <StatusBadge status={node.status} />
      {node.retry_count > 0 && (
        <span style={{ marginLeft: 6, fontSize: "0.7rem", color: "#d97706" }}>↻{node.retry_count}</span>
      )}
      {needsApproval && (
        <button onClick={() => onApprove(node.key)}
          style={{ display: "block", marginTop: 8, background: "#d97706", color: "#fff", border: "none", borderRadius: 4, padding: "3px 10px", fontSize: "0.78rem", cursor: "pointer", width: "100%" }}>
          Onayla ✓
        </button>
      )}
    </div>
  );
}

function Arrow() {
  return <div style={{ color: "#2563eb", fontSize: "1.1rem", alignSelf: "center", flexShrink: 0 }}>→</div>;
}

export default function TaskDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [tools, setTools] = useState<ToolInv[]>([]);
  const [comps, setComps] = useState<Compensation[]>([]);
  const [showCtx, setShowCtx] = useState(false);
  const [ctx, setCtx] = useState<unknown>(null);
  const [actor] = useState("yasin");

  const load = useCallback(async () => {
    const [t, ev, tl, co] = await Promise.all([
      fetch(`${API}/tasks/${id}`).then(r => r.json()),
      fetch(`${API}/tasks/${id}/events`).then(r => r.json()),
      fetch(`${API}/tasks/${id}/tools`).then(r => r.json()),
      fetch(`${API}/tasks/${id}/compensations`).then(r => r.json()),
    ]);
    setTask(t); setEvents(ev.events ?? []); setTools(tl.invocations ?? []); setComps(co.compensations ?? []);
  }, [id]);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [load]);

  async function approveNode(nodeKey: string) {
    await fetch(`${API}/tasks/${id}/nodes/${nodeKey}/approve-node`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor }),
    });
    load();
  }

  async function approveTask() {
    await fetch(`${API}/tasks/${id}/approve`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor }),
    });
    load();
  }

  async function loadCtx() {
    const c = await fetch(`${API}/tasks/${id}/context`).then(r => r.json()).catch(() => null);
    setCtx(c); setShowCtx(true);
  }

  if (!task) return <p style={{ color: "#8b98b8" }}>Yükleniyor…</p>;

  const sortedNodes = [...(task.nodes ?? [])].sort((a, b) => a.key.localeCompare(b.key));
  const needsTaskApproval = task.status === "awaiting_approval";

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.4rem" }}>
            <StatusBadge status={task.status} />
            <span style={{ fontSize: "0.8rem", color: "#8b98b8" }}>{id}</span>
          </div>
          <h1 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0, lineHeight: 1.4 }}>{task.goal}</h1>
        </div>
        {needsTaskApproval && (
          <button onClick={approveTask}
            style={{ background: "#16a34a", color: "#fff", border: "none", borderRadius: 6, padding: "0.5rem 1.2rem", cursor: "pointer", fontWeight: 600 }}>
            Görevi Onayla ✓
          </button>
        )}
      </div>

      {task.error && (
        <div style={{ marginTop: "0.75rem", background: "#1a0a0a", border: "1px solid #dc2626", borderRadius: 6, padding: "0.6rem 0.75rem", fontSize: "0.85rem", color: "#fca5a5" }}>
          ✗ {task.error}
        </div>
      )}

      {/* DAG */}
      <Section title={`DAG — ${sortedNodes.length} düğüm`}>
        <div style={{ display: "flex", gap: "0.5rem", overflowX: "auto", padding: "0.5rem 0" }}>
          {sortedNodes.map((n, i) => (
            <div key={n.key} style={{ display: "flex", gap: "0.5rem" }}>
              {i > 0 && <Arrow />}
              <DAGNode node={n} onApprove={approveNode} />
            </div>
          ))}
        </div>
      </Section>

      {/* Tool Invocations */}
      {tools.length > 0 && (
        <Section title={`Tool Çağrıları (${tools.length})`}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {tools.map((t, i) => (
              <div key={i} style={{ ...card, display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.6rem 0.75rem" }}>
                <span style={{ fontSize: "0.9rem" }}>🔧</span>
                <span style={{ fontWeight: 600, fontSize: "0.85rem", minWidth: 120 }}>{t.tool}</span>
                <StatusBadge status={t.status} />
                {t.dry_run && <span style={{ fontSize: "0.73rem", background: "#1e3a5f", color: "#93c5fd", borderRadius: 4, padding: "1px 6px" }}>dry-run</span>}
                {t.rate_limited && <span style={{ fontSize: "0.73rem", background: "#3b1a1a", color: "#fca5a5", borderRadius: 4, padding: "1px 6px" }}>rate-limited</span>}
                {t.error_code && <span style={{ fontSize: "0.73rem", color: "#fca5a5" }}>{t.error_code}</span>}
                <span style={{ fontSize: "0.75rem", color: "#8b98b8", marginLeft: "auto" }}>node:{t.node_key} attempt:{t.attempt}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Compensations */}
      {comps.length > 0 && (
        <Section title={`Compensation Kayıtları (${comps.length})`}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {comps.map((c, i) => (
              <div key={i} style={{ ...card, display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.6rem 0.75rem", fontSize: "0.85rem" }}>
                <span>↩</span>
                <span style={{ fontWeight: 600 }}>{c.tool}</span>
                <span style={{ color: "#8b98b8" }}>{c.compensate_fn ?? "geri alınamaz"}</span>
                <StatusBadge status={c.status} />
                <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "#8b98b8" }}>{c.created_at ? new Date(c.created_at).toLocaleString("tr-TR") : ""}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Audit Timeline */}
      <Section title={`Denetim Akışı (${events.length} olay)`}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>
          {events.map((ev, i) => (
            <div key={ev.seq} style={{ display: "flex", gap: "0.75rem", padding: "0.5rem 0", borderBottom: i < events.length - 1 ? "1px solid #1e2535" : undefined }}>
              <div style={{ minWidth: 28, textAlign: "right", color: "#475569", fontSize: "0.75rem", paddingTop: 2 }}>{ev.seq}</div>
              <div style={{ width: 3, background: "#1e2535", borderRadius: 2, flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ fontSize: "0.78rem", background: "#1e2535", borderRadius: 4, padding: "1px 6px", color: "#93c5fd" }}>{ev.type}</span>
                  {ev.agent && <span style={{ fontSize: "0.78rem", color: "#8b98b8" }}>{ev.agent}</span>}
                  {ev.node_key && <span style={{ fontSize: "0.78rem", color: "#475569" }}>→ {ev.node_key}</span>}
                </div>
                {ev.payload && Object.keys(ev.payload).length > 0 && (
                  <details style={{ marginTop: 3 }}>
                    <summary style={{ fontSize: "0.75rem", color: "#475569", cursor: "pointer" }}>payload</summary>
                    <pre style={{ fontSize: "0.73rem", color: "#8b98b8", margin: "4px 0 0", overflowX: "auto" }}>
                      {JSON.stringify(ev.payload, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            </div>
          ))}
          {events.length === 0 && <p style={{ color: "#475569", fontSize: "0.85rem" }}>Henüz olay yok.</p>}
        </div>
      </Section>

      {/* Context Snapshot */}
      <Section title="Context">
        {!showCtx ? (
          <button onClick={loadCtx} style={{ background: "#1e2535", color: "#e6e6e6", border: "none", borderRadius: 6, padding: "0.4rem 0.8rem", cursor: "pointer", fontSize: "0.85rem" }}>
            Snapshot Yükle
          </button>
        ) : (
          <pre style={{ ...card, fontSize: "0.75rem", overflowX: "auto", maxHeight: 320 }}>
            {JSON.stringify(ctx, null, 2)}
          </pre>
        )}
      </Section>
    </div>
  );
}
