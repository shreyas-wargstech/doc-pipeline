"use client";
import { createContext, useContext, useEffect, useState } from "react";

type Mode = "light" | "dark";
type ThemeModeCtx = { mode: Mode; toggle: () => void };

const ThemeModeContext = createContext<ThemeModeCtx | null>(null);

export function ThemeModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<Mode>("light");

  useEffect(() => {
    setMode(document.documentElement.classList.contains("dark") ? "dark" : "light");
  }, []);

  const toggle = () => {
    setMode((prev) => {
      const next: Mode = prev === "dark" ? "light" : "dark";
      document.documentElement.classList.toggle("dark", next === "dark");
      try {
        localStorage.setItem("theme", next);
      } catch {
        // ignore (e.g. private browsing)
      }
      return next;
    });
  };

  return <ThemeModeContext.Provider value={{ mode, toggle }}>{children}</ThemeModeContext.Provider>;
}

export function useThemeMode(): ThemeModeCtx {
  const ctx = useContext(ThemeModeContext);
  if (!ctx) throw new Error("useThemeMode must be used within ThemeModeProvider");
  return ctx;
}
