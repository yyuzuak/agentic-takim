import type { ReactNode } from "react";
import Link from "next/link";

export const metadata = {
  title: "Agentic Takım",
  description: "atoms.dev mantığıyla çalışan AI ajan takımı",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="tr">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, background: "#0b0e14", color: "#e6e6e6", minHeight: "100vh" }}>
        <nav style={{ borderBottom: "1px solid #1e2535", padding: "0 1.5rem", display: "flex", alignItems: "center", gap: "1.5rem", height: 52, background: "#0d1117" }}>
          <Link href="/" style={{ fontWeight: 700, fontSize: "1rem", color: "#e6e6e6", textDecoration: "none", letterSpacing: "-0.02em" }}>
            🧭 Agentic Takım
          </Link>
          <div style={{ display: "flex", gap: "1rem", marginLeft: "auto" }}>
            {[["Görevler", "/tasks"], ["Hafıza", "/memory"]].map(([label, href]) => (
              <Link key={href} href={href} style={{ color: "#8b98b8", textDecoration: "none", fontSize: "0.9rem" }}>
                {label}
              </Link>
            ))}
          </div>
        </nav>
        <main style={{ maxWidth: 1100, margin: "0 auto", padding: "2rem 1.5rem" }}>
          {children}
        </main>
      </body>
    </html>
  );
}
