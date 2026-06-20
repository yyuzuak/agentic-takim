"use client";
import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "../../lib/utils";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const isDark = theme === "dark";

  return (
    <button
      aria-label="Tema değiştir"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className={cn(
        "inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors",
        className,
      )}
    >
      {/* mount öncesi ikon flash'ı önlemek için boş alan */}
      {mounted ? (
        isDark ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />
      ) : (
        <span className="w-4 h-4" />
      )}
      <span className="lg:inline hidden">{mounted ? (isDark ? "Koyu" : "Açık") : ""}</span>
    </button>
  );
}
