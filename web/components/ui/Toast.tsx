"use client";
import { CheckCircle2, XCircle } from "lucide-react";
import { useToast } from "@/app/providers";

export function ToastViewport() {
  const { toasts } = useToast();
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-2 rounded-md border bg-card p-3 text-sm shadow-lg ${t.kind === "ok" ? "border-ok/40" : "border-danger/40"}`}
        >
          {t.kind === "ok" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />}
          <span className="text-foreground">{t.message}</span>
        </div>
      ))}
    </div>
  );
}
