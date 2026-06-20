"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, ListChecks, Wrench, Brain, Eye, type LucideIcon } from "lucide-react";
import { cn } from "../lib/utils";
import { ThemeToggle } from "./ui/theme-toggle";

const NAV: { label: string; href: string; icon: LucideIcon }[] = [
  { label: "Studio", href: "/", icon: LayoutGrid },
  { label: "Görevler", href: "/tasks", icon: ListChecks },
  { label: "Araçlar", href: "/tools", icon: Wrench },
  { label: "Hafıza", href: "/memory", icon: Brain },
  { label: "Observer", href: "/observer", icon: Eye },
];

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col bg-sidebar">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 h-16 border-b border-border">
        <span className="grid place-items-center w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-info text-primary-foreground font-bold text-sm shadow-glow">
          ⬡
        </span>
        <div className="leading-tight">
          <p className="text-sm font-semibold tracking-tight">Agentic Takım</p>
          <p className="text-[10px] text-muted-foreground">Agent Studio</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ label, href, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className={cn(
                "relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted",
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-r bg-primary" />
              )}
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Alt: tema + versiyon */}
      <div className="px-3 py-4 border-t border-border space-y-2">
        <ThemeToggle className="w-full justify-start" />
        <p className="px-3 text-[11px] text-muted-foreground">v1.3.1 · Premium UI</p>
      </div>
    </div>
  );
}
