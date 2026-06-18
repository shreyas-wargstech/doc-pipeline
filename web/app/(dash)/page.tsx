"use client";
import { useState } from "react";
import { motion } from "motion/react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { KpiCard } from "@/components/KpiCard";
import { Filters } from "@/components/Filters";
import { DocumentsTable } from "@/components/DocumentsTable";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";
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
  const page = Math.floor(offset / PAGE);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}>
          <KpiCard label="Total" value={Object.values(sc).reduce((a, b) => a + b, 0)} />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}>
          <KpiCard label="Processing" value={sc["processing"] ?? 0} tone="warn" />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}>
          <KpiCard label="Matched" value={mc["matched"] ?? 0} tone="ok" />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}>
          <KpiCard label="Manual review" value={sc["manual_review"] ?? 0} tone="info" />
        </motion.div>
      </div>

      <Filters value={filters} onChange={setFilters} />

      {docs.isLoading ? (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 font-medium"></th>
                <th className="px-3 py-2 font-medium">Reg / File</th>
                <th className="px-3 py-2 font-medium">Category</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Match</th>
                <th className="px-3 py-2 font-medium">OCR</th>
                <th className="px-3 py-2 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-b">
                  <td className="px-3 py-2"><Skeleton className="h-4 w-4" /></td>
                  <td className="px-3 py-2"><Skeleton className="h-4 w-24" /></td>
                  <td className="px-3 py-2"><Skeleton className="h-4 w-20" /></td>
                  <td className="px-3 py-2"><Skeleton className="h-4 w-16" /></td>
                  <td className="px-3 py-2"><Skeleton className="h-4 w-16" /></td>
                  <td className="px-3 py-2"><Skeleton className="h-4 w-24" /></td>
                  <td className="px-3 py-2"><Skeleton className="h-4 w-20" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : docs.isError ? (
        <p className="text-sm text-danger">Failed to load documents.</p>
      ) : (
        <DocumentsTable rows={docs.data!.documents} />
      )}

      <div className="flex items-center justify-end gap-2">
        <span className="text-sm text-muted-foreground">
          {total === 0 ? "0" : `${offset + 1}–${Math.min(offset + PAGE, total)}`} of {total}
        </span>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Previous page"
          disabled={page === 0}
          onClick={() => setFilters({ ...filters, offset: (page - 1) * PAGE })}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Next page"
          disabled={(page + 1) * PAGE >= total}
          onClick={() => setFilters({ ...filters, offset: (page + 1) * PAGE })}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
