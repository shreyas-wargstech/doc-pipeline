"use client";
import { ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

interface Chip { label: string; query: string; accent?: boolean }

export function Composer({
  value, onChange, onSubmit, onSlash, disabled, chips,
}: {
  value: string; onChange: (v: string) => void; onSubmit: () => void;
  onSlash: () => void; disabled?: boolean; chips: Chip[];
}) {
  return (
    <div className="pt-2">
      {chips.length > 0 && (
        <div className="mb-2.5 flex flex-wrap gap-2">
          {chips.map((c) => (
            <button
              key={c.label}
              type="button"
              onClick={() => onChange(c.query)}
              className={cn(
                "rounded-full border px-3 py-1 text-[11px] transition-all duration-200 hover:scale-[1.02] active:scale-95",
                c.accent
                  ? "border-secondary bg-secondary-tint text-secondary-fg hover:bg-secondary-hover hover:text-on-secondary"
                  : "border-border bg-surface-alt text-tertiary-fg hover:bg-surface-hover hover:border-primary/30"
              )}
            >
              {c.label}
            </button>
          ))}
        </div>
      )}
      <Card className="border shadow-lg transition-shadow duration-200 focus-within:shadow-xl focus-within:border-primary/20">
        <div className="flex items-center gap-2 p-2">
          <Input
            role="textbox"
            placeholder="Type / for templates, or ask Aether anything…"
            className="flex-1 border-0 shadow-none focus-visible:ring-0"
            value={value}
            disabled={disabled}
            onChange={(e) => { const v = e.target.value; onChange(v); if (v === "/") onSlash(); }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSubmit(); } }}
          />
          <Button
            size="icon"
            disabled={disabled || !value.trim()}
            onClick={onSubmit}
            aria-label="Send"
            className="transition-transform duration-150 hover:scale-105 active:scale-95"
          >
            <ArrowUp className="h-4 w-4" />
          </Button>
        </div>
      </Card>
    </div>
  );
}
