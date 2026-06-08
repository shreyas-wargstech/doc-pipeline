"use client";
import { KpiCard } from "@/components/KpiCard";
import { MetricBars } from "@/components/MetricBar";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { useMetrics } from "@/hooks/useMetrics";

export default function MetricsPage() {
  const q = useMetrics();
  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError || !q.data) return <p className="text-sm text-danger">Failed to load metrics.</p>;
  const sc = q.data.status_counts;
  const total = Object.values(sc).reduce((a, b) => a + b, 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Total" value={total} />
        <KpiCard label="Processed" value={sc["processed"] ?? 0} tone="ok" />
        <KpiCard label="Processing" value={sc["processing"] ?? 0} tone="warn" />
        <KpiCard label="Failed" value={sc["failed"] ?? 0} tone="danger" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><MetricBars title="By status" data={q.data.status_counts} /></Card>
        <Card><MetricBars title="By match status" data={q.data.match_counts} /></Card>
      </div>
    </div>
  );
}
