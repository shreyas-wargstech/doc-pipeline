"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";

type AccessibilityState = {
  highContrast: boolean;
  largeText: boolean;
  toggleHighContrast: () => void;
  toggleLargeText: () => void;
};

const AccessibilityContext = createContext<AccessibilityState | null>(null);

export function useAccessibility() {
  const ctx = useContext(AccessibilityContext);
  if (!ctx) throw new Error("useAccessibility outside provider");
  return ctx;
}

export function AccessibilityProvider({ children }: { children: React.ReactNode }) {
  const [highContrast, setHighContrast] = useState(false);
  const [largeText, setLargeText] = useState(false);

  useEffect(() => {
    try {
      const hc = window.localStorage.getItem("docintel:high-contrast") === "true";
      const lt = window.localStorage.getItem("docintel:large-text") === "true";
      setHighContrast(hc);
      setLargeText(lt);
      if (hc) document.documentElement.classList.add("high-contrast");
      if (lt) document.documentElement.classList.add("large-text");
    } catch { /* localStorage not available (e.g. SSR) */ }
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("high-contrast", highContrast);
    try { window.localStorage.setItem("docintel:high-contrast", String(highContrast)); } catch { /* */ }
  }, [highContrast]);

  useEffect(() => {
    document.documentElement.classList.toggle("large-text", largeText);
    try { window.localStorage.setItem("docintel:large-text", String(largeText)); } catch { /* */ }
  }, [largeText]);

  const toggleHighContrast = useCallback(() => setHighContrast((p) => !p), []);
  const toggleLargeText = useCallback(() => setLargeText((p) => !p), []);

  return (
    <AccessibilityContext.Provider
      value={{ highContrast, largeText, toggleHighContrast, toggleLargeText }}
    >
      {children}
    </AccessibilityContext.Provider>
  );
}
