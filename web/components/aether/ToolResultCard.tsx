"use client";

import type { ToolResult } from "@/lib/types";
import { AutopsyCard } from "@/components/aether/cards/AutopsyCard";
import { NarrativeCard } from "@/components/aether/cards/NarrativeCard";
import { ContextCard } from "@/components/aether/cards/ContextCard";
import { IdentityCard } from "@/components/aether/cards/IdentityCard";
import { InspectorCard } from "@/components/aether/cards/InspectorCard";
import { HealthCard } from "@/components/aether/cards/HealthCard";
import { SearchResultsCard } from "@/components/aether/cards/SearchResultsCard";

export function ToolResultCard({ result }: { result: ToolResult }) {
  switch (result.kind) {
    case "autopsy":   return <AutopsyCard result={result} />;
    case "narrative": return <NarrativeCard result={result} />;
    case "context":   return <ContextCard result={result} />;
    case "identity":  return <IdentityCard result={result} />;
    case "inspector": return <InspectorCard result={result} />;
    case "health":    return <HealthCard result={result} />;
    case "search":    return <SearchResultsCard result={result} />;
    default:
      return (
        <div
          data-testid="tool-result-fallback"
          className="rounded-lg border border-border bg-surface-alt p-3 text-xs font-mono overflow-auto max-h-48"
        >
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      );
  }
}
