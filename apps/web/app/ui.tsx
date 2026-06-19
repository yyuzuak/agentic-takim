"use client";
import type { CSSProperties } from "react";

export const card: CSSProperties = {
  background: "#11151f",
  border: "1px solid #1e2535",
  borderRadius: 8,
  padding: "1rem",
};

const STATUS_COLORS: Record<string, [string, string]> = {
  done:               ["#16a34a", "#dcfce7"],
  running:            ["#2563eb", "#dbeafe"],
  in_progress:        ["#2563eb", "#dbeafe"],
  pending:            ["#475569", "#e2e8f0"],
  failed:             ["#dc2626", "#fee2e2"],
  awaiting_approval:  ["#d97706", "#fef3c7"],
  blocked:            ["#b45309", "#fef3c7"],
  scheduled:          ["#7c3aed", "#ede9fe"],
};

export function StatusBadge({ status }: { status: string }) {
  const [bg, text] = STATUS_COLORS[status] ?? ["#334155", "#e2e8f0"];
  return (
    <span style={{ background: bg, color: text, borderRadius: 4, padding: "2px 7px", fontSize: "0.75rem", fontWeight: 600, whiteSpace: "nowrap" }}>
      {status}
    </span>
  );
}

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: "1.5rem" }}>
      <h2 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "0.75rem", color: "#8b98b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>{title}</h2>
      {children}
    </div>
  );
}
