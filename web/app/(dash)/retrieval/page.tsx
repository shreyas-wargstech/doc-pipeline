import { ComingSoon } from "@/components/ComingSoon";

export default function RetrievalPage() {
  return (
    <ComingSoon
      title="Retrieval"
      items={[
        "Query input with filters",
        "Answer panel with source citations",
        "Chunk list with relevance scores",
        "Similarity / ranking explanation",
        "Debug and trace view",
        "Comparison view across queries",
      ]}
    />
  );
}
