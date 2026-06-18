import { ResultCard } from "@/components/retrieval/ResultCard";
import type { RetrievalHit } from "@/lib/types";

export function ResultsList({
  hits,
  selectedId,
  onSelect,
  isLoading,
  isError,
  query,
}: {
  hits: RetrievalHit[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  isLoading: boolean;
  isError?: boolean;
  query: string;
}) {
  if (!query) {
    return <p className="px-1 text-sm text-muted-fg">Enter a query to search.</p>;
  }
  if (isLoading) {
    return (
      <div className="flex flex-col gap-1.5" aria-busy="true" aria-label="Loading search results">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 animate-pulse rounded-panel border border-border bg-surface-alt" />
        ))}
      </div>
    );
  }
  if (isError) {
    return (
      <p className="text-sm text-danger px-1">Search failed. Please try again.</p>
    );
  }
  if (hits.length === 0) {
    return <p className="px-1 text-sm text-muted-fg">No results for "{query}".</p>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="px-1 text-xs text-muted-fg">{hits.length} result{hits.length === 1 ? "" : "s"}</div>
      {hits.map((h) => (
        <ResultCard
          key={h.document_id}
          hit={h}
          selected={h.document_id === selectedId}
          onClick={() => onSelect(h.document_id)}
        />
      ))}
    </div>
  );
}
