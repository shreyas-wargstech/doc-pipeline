"use client";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

export function JsonViewer({ data, title = "structured_json" }: { data: unknown; title?: string }) {
  const [open, setOpen] = useState(true);
  const text = data == null ? "null" : JSON.stringify(data, null, 2);

  // Simple token-based syntax highlighting — safe, no regex HTML injection.
  const tokens = text.split(/("(?:\\.|[^"\\])*"|\b(?:true|false|null)\b|\d+|[:{},\[\]]|\s+)/g).filter(Boolean);

  return (
    <div className="rounded-panel border border-border bg-surface">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium text-foreground hover:bg-surface-hover cursor-pointer"
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        {title}
      </button>
      {open && (
        <pre className="max-h-[60vh] overflow-auto border-t border-border px-3 py-2 font-mono text-xs leading-relaxed">
          {tokens.map((token, i) => {
            const nextToken = tokens[i + 1];
            const isKey = /^"(?:\\.|[^"\\])*"$/.test(token) && nextToken?.trimStart().startsWith(":");
            if (isKey) {
              return <span key={i} className="text-primary">{token}</span>;
            }
            if (/^"(?:\\.|[^"\\])*"$/.test(token)) {
              return <span key={i} className="text-success">{token}</span>;
            }
            if (/^\b(?:true|false|null)\b$/.test(token)) {
              return <span key={i} className="text-info">{token}</span>;
            }
            if (/^\d+$/.test(token)) {
              return <span key={i} className="text-warn">{token}</span>;
            }
            return <span key={i} className="text-foreground">{token}</span>;
          })}
        </pre>
      )}
    </div>
  );
}
