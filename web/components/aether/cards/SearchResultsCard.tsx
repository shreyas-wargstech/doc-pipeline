"use client";
import Link from "next/link";
import { FileText, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/Card";
import type { ToolResult } from "@/lib/types";

export function SearchResultsCard({ result }: { result: Extract<ToolResult, { kind: "search" }> }) {
  if (result.total === 0) {
    return <Card className="border p-3"><p className="text-sm text-muted-foreground">No documents found.</p></Card>;
  }
  return (
    <div className="space-y-2">
      <div className="grid gap-2">
        {result.hits.map((h) => (
          <Link key={h.document_id} href={`/documents/${h.document_id}`}
            className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5 transition-colors hover:bg-surface-hover">
            <FileText className="h-4.5 w-4.5 text-primary shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium capitalize">{h.document_type ?? "document"}</div>
              <div className="text-[11px] text-muted-foreground font-mono truncate">
                {h.document_id.slice(0, 12)}…{h.page_type ? ` · ${h.page_type}` : ""}
              </div>
            </div>
          </Link>
        ))}
      </div>
      <Link href="/retrieval" className="inline-flex items-center gap-1 text-xs text-primary">
        See all in retrieval <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  );
}
