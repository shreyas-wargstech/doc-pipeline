"use client";
import { Moon, Sun } from "lucide-react";
import { useThemeMode } from "@/app/theme-mode";

export function ThemeToggle() {
  const { mode, toggle } = useThemeMode();
  return (
    <button onClick={toggle} aria-label="Toggle theme"
      className="inline-flex h-11 w-11 items-center justify-center rounded-md text-foreground hover:bg-muted cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {mode === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </button>
  );
}
