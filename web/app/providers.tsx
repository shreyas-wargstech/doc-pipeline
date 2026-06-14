"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { EmotionRegistry } from "./EmotionRegistry";
import { ActionBarProvider } from "./action-bar";

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: false, retry: 1 } },
});

export type Toast = { id: number; kind: "ok" | "error"; message: string };
type ToastCtx = { toasts: Toast[]; push: (kind: Toast["kind"], message: string) => void };
const ToastContext = createContext<ToastCtx | null>(null);
export const useToast = () => {
  const c = useContext(ToastContext);
  if (!c) throw new Error("useToast outside provider");
  return c;
};

/** Like useToast, but returns a no-op push() instead of throwing when used outside a provider (e.g. in tests). */
export const useToastSafe = (): ToastCtx["push"] => {
  const c = useContext(ToastContext);
  return c?.push ?? (() => {});
};

export function Providers({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const idRef = useRef(0);
  const push = useCallback((kind: Toast["kind"], message: string) => {
    const id = ++idRef.current;
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  const value = useMemo(() => ({ toasts, push }), [toasts, push]);
  return (
    <EmotionRegistry>
      <QueryClientProvider client={qc}>
        <ToastContext.Provider value={value}>
          <ActionBarProvider>{children}</ActionBarProvider>
        </ToastContext.Provider>
      </QueryClientProvider>
    </EmotionRegistry>
  );
}
