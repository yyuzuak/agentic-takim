import type { ReactNode } from "react";
import Link from "next/link";
import "./globals.css";
import { Providers } from "./components/providers";

export const metadata = {
  title: "Agentic Takım — Agent Studio",
  description: "atoms.dev mantığıyla çalışan AI ajan takımı operasyon platformu",
};

const NAV = [
  { label: "Studio",    href: "/" },
  { label: "Görevler", href: "/tasks" },
  { label: "Araçlar",  href: "/tools" },
  { label: "Hafıza",   href: "/memory" },
  { label: "Observer", href: "/observer" },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="tr" className="dark">
      <body className="min-h-screen bg-background text-foreground antialiased">
        <Providers>
          <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur">
            <div className="mx-auto max-w-7xl px-4 sm:px-6 flex items-center h-14 gap-6">
              <Link href="/" className="flex items-center gap-2 font-semibold text-sm text-foreground hover:text-primary transition-colors">
                <span className="text-primary">⬡</span> Agentic Takım
              </Link>
              <nav className="flex items-center gap-1 ml-4">
                {NAV.map(({ label, href }) => (
                  <Link
                    key={href}
                    href={href}
                    className="px-3 py-1.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  >
                    {label}
                  </Link>
                ))}
              </nav>
              <div className="ml-auto flex items-center gap-2">
                <span className="text-xs text-muted-foreground">v1.2</span>
              </div>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-4 sm:px-6 py-6">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
