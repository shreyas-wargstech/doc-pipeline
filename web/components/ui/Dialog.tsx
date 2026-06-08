"use client";
import { useEffect } from "react";
import { Button } from "./Button";

export function ConfirmDialog({
  open, title, body, confirmLabel = "Confirm", destructive, loading, onConfirm, onCancel,
}: {
  open: boolean; title: string; body?: string; confirmLabel?: string;
  destructive?: boolean; loading?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onCancel} aria-hidden />
      <div className="relative w-full max-w-md rounded-lg border bg-card p-5 shadow-lg">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        {body && <p className="mt-2 text-sm text-muted-fg">{body}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button variant={destructive ? "destructive" : "primary"} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
