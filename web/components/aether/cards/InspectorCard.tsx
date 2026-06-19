"use client";
import { motion } from "motion/react";
import { Route, Check } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { ToolResult } from "@/lib/types";

const RAIL = ["Ingest", "OCR", "Structure", "Match", "Persist", "Index"];

export function InspectorCard({ result }: { result: Extract<ToolResult, { kind: "inspector" }> }) {
  const byName = new Map(result.stages.map((s) => [s.stage.toLowerCase(), s.status]));
  const statuses = RAIL.map((label) => byName.get(label.toLowerCase()) ?? "pending");
  const doneCount = statuses.filter((s) => s === "success").length;
  const pct = Math.round((doneCount / RAIL.length) * 100);

  return (
    <Card className="border p-3">
      <div className="flex items-center gap-2 mb-4">
        <Route className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">Pipeline progress</span>
        <Badge tone={result.overall_status === "processed" ? "ok" : "warn"} className="ml-auto">
          {result.overall_status}
        </Badge>
      </div>
      <div className="relative px-1">
        <div className="absolute left-2.5 right-2.5 top-2.5 h-0.5 bg-border" />
        <motion.div className="absolute left-2.5 top-2.5 h-0.5 bg-ok"
          initial={{ width: 0 }} animate={{ width: `calc(${pct}% - 5px)` }}
          transition={{ duration: 0.7, ease: "easeOut" }} />
        <div className="relative flex justify-between">
          {RAIL.map((label, i) => {
            const st = statuses[i];
            const done = st === "success";
            const active = st !== "success" && st !== "pending";
            return (
              <div key={label} className="flex flex-col items-center gap-1.5">
                <span className={`flex h-5 w-5 items-center justify-center rounded-full ${
                  done ? "bg-ok text-white"
                  : active ? "border-2 border-warn bg-surface"
                  : "border-2 border-border bg-surface"}`}>
                  {done && <Check className="h-3 w-3" />}
                  {active && <span className="h-1.5 w-1.5 rounded-full bg-warn" />}
                </span>
                <span className={`text-[10px] ${active ? "text-warn font-medium" : done ? "text-tertiary-fg" : "text-muted-fg"}`}>
                  {label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}
