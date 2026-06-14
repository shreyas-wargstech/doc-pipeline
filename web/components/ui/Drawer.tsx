"use client";
import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

/**
 * Right-side slide-in panel. Mirrors ConfirmDialog conventions: role="dialog",
 * Escape to close, backdrop click to close, focus moved to the panel on open.
 */
export function Drawer({
  open, title, onClose, children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open]);

  if (!open) return null;
  return (
    <div role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden />
      <div
        ref={panelRef}
        tabIndex={-1}
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto border-l bg-card shadow-lg focus:outline-none"
      >
        <div className="sticky top-0 flex items-center justify-between gap-3 border-b bg-card px-4 py-3">
          <h2 className="text-base font-semibold text-foreground">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-muted-fg hover:bg-muted hover:text-foreground cursor-pointer">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex flex-col gap-4 p-4">{children}</div>
      </div>
    </div>
  );
}
