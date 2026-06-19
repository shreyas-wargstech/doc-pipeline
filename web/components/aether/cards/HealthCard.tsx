"use client";
import { Activity } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { ToolResult } from "@/lib/types";

function dot(status: string) {
  if (status === "ok") return "var(--color-ok)";
  if (status === "warn") return "var(--color-warn)";
  if (status === "error") return "var(--color-danger)";
  return "var(--color-tertiary-fg)";
}

export function HealthCard({ result }: { result: Extract<ToolResult, { kind: "health" }> }) {
  return (
    <Card className="border p-3">
      <div className="flex items-center gap-2 mb-3">
        <Activity className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">System health</span>
        <Badge tone={result.overall === "ok" ? "ok" : result.overall === "warn" ? "warn" : "danger"} className="ml-auto">
          {result.overall}
        </Badge>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {result.checks.map((c) => (
          <div key={c.name} className="rounded-lg bg-surface-alt p-2.5">
            <div className="flex items-center gap-1.5 mb-1">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: dot(c.status) }} />
              <span className="text-[11px] capitalize text-tertiary-fg truncate">{c.name}</span>
            </div>
            <div className="text-xs font-mono">
              {c.latency_ms !== undefined ? `${c.latency_ms}ms` : c.status}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
