"use client";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

export function JsonViewer({ data, title = "structured_json" }: { data: unknown; title?: string }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="rounded-lg border bg-card">
      <button onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium text-foreground hover:bg-muted cursor-pointer">
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}{title}
      </button>
      {open && (
        <pre className="max-h-[60vh] overflow-auto border-t px-3 py-2 font-mono text-xs leading-relaxed text-foreground">
          {data == null ? "null" : JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
