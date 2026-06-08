"use client";
import { useState } from "react";
import { KpiCard } from "@/components/KpiCard";
import { Filters } from "@/components/Filters";
import { DocumentsTable } from "@/components/DocumentsTable";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { useDocuments, type DocFilters } from "@/hooks/useDocuments";
import { useMetrics } from "@/hooks/useMetrics";

const PAGE = 50;

export default function DocumentsHome() {
  const [filters, setFilters] = useState<DocFilters>({});
  const docs = useDocuments(filters);
  const metrics = useMetrics();
  const offset = filters.offset ?? 0;
  const total = docs.data?.total ?? 0;
  const sc = metrics.data?.status_counts ?? {};
  const mc = metrics.data?.match_counts ?? {};

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Total" value={Object.values(sc).reduce((a, b) => a + b, 0)} />
        <KpiCard label="Processing" value={sc["processing"] ?? 0} tone="warn" />
        <KpiCard label="Matched" value={mc["matched"] ?? 0} tone="ok" />
        <KpiCard label="Manual review" value={(sc["manual_review"] ?? 0) + (mc["manual_review"] ?? 0)} tone="info" />
      </div>

      <Filters value={filters} onChange={setFilters} />

      {docs.isLoading ? (
        <div className="flex flex-col gap-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
      ) : docs.isError ? (
        <p className="text-sm text-danger">Failed to load documents.</p>
      ) : (
        <DocumentsTable rows={docs.data!.documents} />
      )}

      <div className="flex items-center justify-between text-sm text-muted-fg">
        <span className="tnum">{total ? `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}` : "0"}</span>
        <div className="flex gap-2">
          <Button variant="secondary" disabled={offset === 0} onClick={() => setFilters({ ...filters, offset: Math.max(0, offset - PAGE) })}>Prev</Button>
          <Button variant="secondary" disabled={offset + PAGE >= total} onClick={() => setFilters({ ...filters, offset: offset + PAGE })}>Next</Button>
        </div>
      </div>
    </div>
  );
}
