"use client";
import { useMemo, useState, useEffect } from "react";
import { CornerDownLeft } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";
import { TEMPLATES, type QueryTemplate } from "@/components/aether/templates";

const GROUPS: QueryTemplate["group"][] = ["Diagnose", "Find", "System"];

export function CommandPalette({
  open, onOpenChange, onSelect,
}: { open: boolean; onOpenChange: (o: boolean) => void; onSelect: (query: string) => void }) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);

  const filtered = useMemo(
    () => TEMPLATES.filter((t) => t.label.toLowerCase().includes(q.toLowerCase()) || t.hint.toLowerCase().includes(q.toLowerCase())),
    [q],
  );
  useEffect(() => { if (open) { setQ(""); setActive(0); } }, [open]);

  const pick = (t: QueryTemplate) => { onSelect(t.query); onOpenChange(false); };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 overflow-hidden max-w-md">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <input autoFocus value={q} placeholder="Search templates…"
          onChange={(e) => { setQ(e.target.value); setActive(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
            if (e.key === "Enter" && filtered[active]) { e.preventDefault(); pick(filtered[active]); }
          }}
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm outline-none" />
        <div className="max-h-80 overflow-y-auto p-2">
          {GROUPS.map((g) => {
            const items = filtered.filter((t) => t.group === g);
            if (!items.length) return null;
            return (
              <div key={g}>
                <div className="px-2 pt-2 pb-1 text-[10px] uppercase tracking-wider text-muted-fg">{g}</div>
                {items.map((t) => {
                  const idx = filtered.indexOf(t);
                  return (
                    <button key={t.id} type="button" onMouseEnter={() => setActive(idx)} onClick={() => pick(t)}
                      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left ${idx === active ? "bg-primary-tint" : ""}`}>
                      <div className="flex-1 min-w-0">
                        <div className="text-[13px] font-medium">{t.label}</div>
                        <div className="text-[11px] text-muted-fg">{t.hint}</div>
                      </div>
                      {idx === active && <CornerDownLeft className="h-4 w-4 text-primary" />}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
        <div className="flex items-center gap-3 border-t border-border bg-surface-alt px-4 py-2 text-[10.5px] text-muted-fg">
          <span>↑↓ navigate</span><span>↵ select</span>
          <span className="ml-auto">free · instant · no LLM</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
