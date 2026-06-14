"use client";
import { useCallback, useEffect, useState } from "react";

/**
 * SSR-safe boolean toggle persisted to localStorage under `collapse:<key>`.
 * Starts from `defaultCollapsed` on the server / first render, then reconciles
 * with any stored value after mount (avoids hydration mismatch).
 */
export function useCollapsible(key: string, defaultCollapsed = false) {
  const storageKey = `collapse:${key}`;
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  useEffect(() => {
    const stored = window.localStorage.getItem(storageKey);
    if (stored !== null) setCollapsed(stored === "true");
  }, [storageKey]);

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      window.localStorage.setItem(storageKey, String(next));
      return next;
    });
  }, [storageKey]);

  return { collapsed, toggle };
}
