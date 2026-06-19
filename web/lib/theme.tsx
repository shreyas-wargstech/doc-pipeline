"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

type Theme = "system" | "light" | "dark";
type Resolved = "light" | "dark";

type ThemeState = {
  theme: Theme;
  resolvedTheme: Resolved;
  cycleTheme: () => void;
};

const ThemeContext = createContext<ThemeState | null>(null);
const STORAGE_KEY = "docintel:theme";
const ORDER: Theme[] = ["system", "light", "dark"];

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme outside provider");
  return ctx;
}

function systemPrefersDark(): boolean {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return false;
  }
}

function resolve(theme: Theme): Resolved {
  if (theme === "system") return systemPrefersDark() ? "dark" : "light";
  return theme;
}

function applyClass(resolved: Resolved) {
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("system");
  const [resolvedTheme, setResolvedTheme] = useState<Resolved>("light");

  // Hydrate React state from storage (class was already set pre-paint by the inline script).
  useEffect(() => {
    let initial: Theme = "system";
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "light" || stored === "dark" || stored === "system") initial = stored;
    } catch { /* localStorage unavailable */ }
    setTheme(initial);
  }, []);

  // Apply class + persist whenever the chosen theme changes.
  useEffect(() => {
    const r = resolve(theme);
    setResolvedTheme(r);
    applyClass(r);
    try { window.localStorage.setItem(STORAGE_KEY, theme); } catch { /* */ }
  }, [theme]);

  // While in system mode, follow live OS preference changes.
  useEffect(() => {
    if (theme !== "system") return;
    let mql: MediaQueryList;
    try { mql = window.matchMedia("(prefers-color-scheme: dark)"); }
    catch { return; }
    const onChange = () => {
      const r: Resolved = systemPrefersDark() ? "dark" : "light";
      setResolvedTheme(r);
      applyClass(r);
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [theme]);

  const cycleTheme = useCallback(() => {
    setTheme((t) => ORDER[(ORDER.indexOf(t) + 1) % ORDER.length]);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, cycleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
