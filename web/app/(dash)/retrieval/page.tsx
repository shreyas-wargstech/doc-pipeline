"use client";
import { useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { DetailPanel } from "@/components/retrieval/DetailPanel";
import { ResultsList } from "@/components/retrieval/ResultsList";
import { SearchBar } from "@/components/retrieval/SearchBar";
import { useSearch } from "@/hooks/useSearch";

export default function RetrievalPage() {
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, isLoading } = useSearch(submittedQuery);

  const handleSearch = (q: string) => {
    setSubmittedQuery(q);
    setSelectedId(null);
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-4">
      <PageHeader
        title="Retrieval"
        subtitle="Search across indexed practitioner documents — keyword, graph, and semantic."
      />
      <SearchBar onSearch={handleSearch} disabled={isLoading} />
      <div className="flex min-h-0 flex-1 gap-3">
        <div className="w-[380px] shrink-0 overflow-y-auto">
          <ResultsList
            hits={data?.hits ?? []}
            selectedId={selectedId}
            onSelect={setSelectedId}
            isLoading={isLoading}
            query={submittedQuery}
          />
        </div>
        <DetailPanel documentId={selectedId} />
      </div>
    </div>
  );
}
