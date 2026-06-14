"use client";
import Link from "next/link";
import { PageRow } from "@/components/retrieval/PageRow";
import { useSearchDocPages } from "@/hooks/useSearch";

function shortId(id: string): string {
  return id.length > 16 ? `${id.slice(0, 12)}…${id.slice(-4)}` : id;
}

export function DetailPanel({ documentId }: { documentId: string | null }) {
  const { data, isLoading, isError } = useSearchDocPages(documentId);

  return (
    <div className="flex flex-1 flex-col overflow-hidden rounded-panel border border-border bg-surface">
      {documentId === null ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-muted-fg">
          <p className="text-sm">Select a result to see its pages.</p>
        </div>
      ) : isError ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-red-600">Failed to load pages.</p>
        </div>
      ) : isLoading || !data ? (
        <div className="flex flex-1 items-center justify-center text-sm text-muted-fg" aria-busy="true">
          Loading pages…
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <div className="font-mono text-xs font-semibold text-foreground">{shortId(data.document_id)}</div>
              <div className="text-xs text-muted-fg">{data.count} page{data.count === 1 ? "" : "s"}</div>
            </div>
            <Link href={`/documents/${data.document_id}`} className="text-xs font-medium text-primary hover:underline">
              Open in viewer ↗
            </Link>
          </div>
          <div className="flex flex-1 flex-col gap-2.5 overflow-y-auto p-3">
            {data.hits.map((h) => (
              <PageRow key={h.page_id} hit={h} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
