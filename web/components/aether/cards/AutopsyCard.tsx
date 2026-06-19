"use client";
import { motion } from "motion/react";
import { Info } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { ToolResult } from "@/lib/types";

function dot(status: string) {
  if (status === "success") return "var(--color-ok)";
  if (status === "failed") return "var(--color-danger)";
  if (status === "manual_review" || status === "partial") return "var(--color-warn)";
  return "var(--color-tertiary-fg)";
}

export function AutopsyCard({ result }: { result: Extract<ToolResult, { kind: "autopsy" }> }) {
  return (
    <Card className="border overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <span className="text-sm font-medium">Autopsy</span>
        <Badge tone="warn" className="ml-auto">{result.overall_status.replace("_", " ")}</Badge>
      </div>
      <div className="p-3 space-y-2">
        {result.stages.map((s, i) => (
          <motion.div key={s.name} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }} className="flex items-center gap-2.5 text-xs">
            <span className="h-2 w-2 rounded-full shrink-0" style={{ background: dot(s.status) }} />
            <span className="w-20 capitalize text-tertiary-fg">{s.name}</span>
            <span className="text-muted-fg flex-1">{s.detail}</span>
          </motion.div>
        ))}
        {result.recommendation && (
          <div className="mt-2 flex gap-2 rounded-lg border border-secondary/20 bg-secondary-tint p-2.5">
            <Info className="h-4 w-4 text-secondary shrink-0 mt-0.5" />
            <p className="text-xs text-foreground">{result.recommendation}</p>
          </div>
        )}
      </div>
    </Card>
  );
}
