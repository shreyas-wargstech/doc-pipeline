"use client";
import { motion } from "motion/react";
import { ShieldCheck, Check, Minus } from "lucide-react";
import { Card } from "@/components/ui/Card";
import type { ToolResult } from "@/lib/types";

const R = 42, C = 2 * Math.PI * R;

export function IdentityCard({ result }: { result: Extract<ToolResult, { kind: "identity" }> }) {
  const score = Math.max(0, Math.min(100, Math.round(result.consistency_score)));
  const offset = C * (1 - score / 100);
  return (
    <Card className="border overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <ShieldCheck className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">Identity consistency</span>
      </div>
      <div className="p-4 flex gap-4 items-center">
        <div className="relative h-24 w-24 shrink-0">
          <svg viewBox="0 0 100 100" className="h-24 w-24">
            <circle cx="50" cy="50" r={R} fill="none" stroke="var(--color-surface-alt)" strokeWidth="9" />
            <motion.circle cx="50" cy="50" r={R} fill="none" stroke="var(--color-ok)" strokeWidth="9"
              strokeLinecap="round" strokeDasharray={C} transform="rotate(-90 50 50)"
              initial={{ strokeDashoffset: C }} animate={{ strokeDashoffset: offset }}
              transition={{ duration: 0.8, ease: "easeOut" }} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-display font-medium">{score}</span>
            <span className="text-[9px] text-muted-fg">/ 100</span>
          </div>
        </div>
        <div className="flex-1">
          {result.summary && <p className="text-xs leading-relaxed text-foreground mb-2">{result.summary}</p>}
          <div className="space-y-1.5">
            {(result.fields ?? []).map((f) => {
              const ok = f.agree && f.present_pages === f.total_pages;
              return (
                <div key={f.field} className="flex items-center gap-2 text-xs">
                  {ok ? <Check className="h-3.5 w-3.5 text-ok" /> : <Minus className="h-3.5 w-3.5 text-warn" />}
                  <span className="text-tertiary-fg capitalize">{f.field}</span>
                  <span className="ml-auto text-muted-fg">{f.present_pages}/{f.total_pages} pages</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Card>
  );
}
