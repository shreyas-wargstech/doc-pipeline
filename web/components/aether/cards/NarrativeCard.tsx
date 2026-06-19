"use client";
import Link from "next/link";
import { FileText } from "lucide-react";
import { Card } from "@/components/ui/Card";
import type { ToolResult } from "@/lib/types";

export function NarrativeCard({ result }: { result: Extract<ToolResult, { kind: "narrative" }> }) {
  return (
    <Card className="border p-3 transition-shadow duration-200 hover:shadow-md">
      <p className="text-sm leading-relaxed text-foreground">{result.narrative}</p>
      <Link href={`/documents/${result.document_id}`}
        className="mt-2 inline-flex items-center gap-1 text-xs text-primary transition-colors hover:underline">
        <FileText className="h-3.5 w-3.5" /> Open document
      </Link>
    </Card>
  );
}
