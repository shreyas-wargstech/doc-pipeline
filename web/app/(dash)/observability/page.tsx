"use client";
import { useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { KpiCard } from "@/components/KpiCard";
import { MetricBars } from "@/components/MetricBar";
import { AuditActivity } from "@/components/AuditActivity";
import { AuditTable } from "@/components/AuditTable";
import { AuditDetailDrawer } from "@/components/AuditDetailDrawer";
import { CostSection } from "@/components/CostSection";
import { useMetrics } from "@/hooks/useMetrics";
import { useAudit, type AuditFilters } from "@/hooks/useAudit";
import type { AuditRow } from "@/lib/types";

export default function ObservabilityPage() {
  const metrics = useMetrics();
  const [filters, setFilters] = useState<AuditFilters>({});
  const audit = useAudit(filters);
  const [selected, setSelected] = useState<AuditRow | null>(null);

  const sc = metrics.data?.status_counts ?? {};
  const mc = metrics.data?.match_counts ?? {};
  const total = Object.values(sc).reduce((a, b) => a + b, 0);
  const rows = audit.data?.rows ?? [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Observability"
        subtitle="Pipeline health and the dashboard control-action event log."
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Total" value={total} />
        <KpiCard label="Processing" value={sc["processing"] ?? 0} tone="warn" />
        <KpiCard label="Manual review" value={sc["manual_review"] ?? 0} tone="info" />
        <KpiCard label="Failed" value={sc["failed"] ?? 0} tone="danger" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card><MetricBars title="By status" data={sc} /></Card>
        <Card><MetricBars title="By match status" data={mc} /></Card>
        <Card><AuditActivity rows={rows} /></Card>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="font-display text-lg font-semibold text-foreground">Event log</h2>
        <div className="flex flex-wrap gap-2">
          <Input className="max-w-[12rem]" placeholder="username"
            value={filters.username ?? ""}
            onChange={(e) => setFilters({ ...filters, username: e.target.value || undefined })} />
          <Input className="max-w-[12rem]" placeholder="action"
            value={filters.action ?? ""}
            onChange={(e) => setFilters({ ...filters, action: e.target.value || undefined })} />
          <Input className="max-w-[20rem] font-mono" placeholder="document_id"
            value={filters.document_id ?? ""}
            onChange={(e) => setFilters({ ...filters, document_id: e.target.value || undefined })} />
          <Select aria-label="result"
            value={filters.result ?? ""}
            onChange={(e) => setFilters({ ...filters, result: e.target.value || undefined })}>
            <option value="">All results</option>
            <option value="ok">ok</option>
            <option value="error">error</option>
          </Select>
        </div>

        {audit.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : audit.isError || !audit.data ? (
          <p className="text-sm text-danger">Failed to load the event log.</p>
        ) : (
          <AuditTable rows={rows} onRowClick={setSelected} />
        )}
      </section>

      <CostSection />

      <p className="text-xs text-muted-fg">
        Per-stage latency and OpenRouter credit balance are not yet instrumented.
      </p>

      <AuditDetailDrawer row={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
