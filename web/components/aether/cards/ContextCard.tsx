"use client";
import { Link2 } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { ToolResult } from "@/lib/types";

export function ContextCard({ result }: { result: Extract<ToolResult, { kind: "context" }> }) {
  const related = result.related_documents ?? [];
  return (
    <Card className="border p-3">
      <div className="flex items-center gap-2 mb-2">
        <Link2 className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">Context</span>
        <Badge tone="muted" className="ml-auto text-[10px]">{related.length} related</Badge>
      </div>
      {result.practitioner_history ? (
        <p className="text-xs text-muted-fg">Practitioner history available.</p>
      ) : (
        <p className="text-xs text-muted-fg">No practitioner history found.</p>
      )}
    </Card>
  );
}
