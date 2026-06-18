"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:8000";

type Health = { status: string; features: Record<string, boolean> };
type Agent = { id: string; display_name: string; role: string; type: string; skills: string[] };

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const h = await fetch(`${API}/health`).then((r) => r.json());
        setHealth(h);
        const a = await fetch(`${API}/agents`).then((r) => r.json());
        setAgents(a.agents ?? []);
      } catch (e) {
        setError(String(e));
      }
    })();
  }, []);

  return (
    <main style={{ maxWidth: 880, margin: "0 auto", padding: "3rem 1.5rem" }}>
      <h1 style={{ fontSize: "2rem" }}>🧭 Agentic Takım</h1>
      <p style={{ opacity: 0.7 }}>Control-plane: <code>{API}</code></p>

      <section style={{ marginTop: "2rem" }}>
        <h2>Durum</h2>
        {error && <p style={{ color: "#ff6b6b" }}>Control-plane'e ulaşılamadı: {error}</p>}
        {health ? (
          <pre style={{ background: "#11151f", padding: "1rem", borderRadius: 8 }}>
            {JSON.stringify(health, null, 2)}
          </pre>
        ) : (
          !error && <p>Yükleniyor…</p>
        )}
      </section>

      <section style={{ marginTop: "2rem" }}>
        <h2>Takım ({agents.length})</h2>
        <div style={{ display: "grid", gap: "0.75rem" }}>
          {agents.map((a) => (
            <div key={a.id} style={{ background: "#11151f", padding: "1rem", borderRadius: 8 }}>
              <strong>{a.display_name}</strong> <span style={{ opacity: 0.6 }}>· {a.role}</span>
              <div style={{ marginTop: 6, fontSize: "0.85rem", opacity: 0.75 }}>
                {a.skills.join(" · ")}
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
