"use client";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { Table, type Column } from "@/components/ui/Table";
import { KpiCard } from "@/components/KpiCard";
import { MetricBars } from "@/components/MetricBar";
import { fmtDateTime, fmtUsd } from "@/lib/format";
import { useCosts, useCostEvents } from "@/hooks/useCosts";
import type { CostBreakdownEntry, CostEventRow } from "@/lib/types";

function costMap(rec: Record<string, CostBreakdownEntry>): Record<string, number> {
  // MetricBars wants Record<string, number>; round USD to 4dp so the label reads sanely.
  return Object.fromEntries(Object.entries(rec).map(([k, v]) => [k, Math.round(v.cost * 10000) / 10000]));
}

const columns: Column<CostEventRow>[] = [
  { key: "ts", header: "When", className: "tnum text-muted-fg", render: (r) => fmtDateTime(r.ts) },
  { key: "stage", header: "Stage", render: (r) => <span className="font-mono text-xs">{r.stage}</span> },
  { key: "model", header: "Model", className: "max-w-[14rem] truncate text-muted-fg" },
  { key: "document_id", header: "Document", className: "font-mono text-xs",
    render: (r) => (r.document_id ? r.document_id : "—") },
  { key: "total_tokens", header: "Tokens", className: "tnum text-right" },
  { key: "cost", header: "Cost", className: "tnum text-right", render: (r) => fmtUsd(r.cost) },
  { key: "status", header: "Status", render: (r) => <Badge tone={r.status === "ok" ? "ok" : "danger"}>{r.status}</Badge> },
];

export function CostSection() {
  const costs = useCosts();
  const events = useCostEvents();

  if (costs.isLoading) return <Skeleton className="h-48 w-full" />;
  if (costs.isError || !costs.data) {
    return <p className="text-sm text-danger">Failed to load cost data.</p>;
  }

  const { summary, by_stage, by_model } = costs.data;
  const rows = events.data?.rows ?? [];

  return (
    <section className="flex flex-col gap-4">
      <h2 className="font-display text-lg font-semibold text-foreground">Cost &amp; usage</h2>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Total spend" value={fmtUsd(summary.cost)} />
        <KpiCard label="Total tokens" value={summary.total_tokens} />
        <KpiCard label="LLM calls" value={summary.calls} />
        <KpiCard label="Errors" value={summary.errors} tone={summary.errors ? "danger" : "ok"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card><MetricBars title="Cost by stage (USD)" data={costMap(by_stage)} /></Card>
        <Card><MetricBars title="Cost by model (USD)" data={costMap(by_model)} /></Card>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-foreground">Recent calls</h3>
        {events.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <Table columns={columns} rows={rows} rowKey={(r) => String(r.id)} empty="No cost events recorded yet." />
        )}
      </div>
    </section>
  );
}
