"use client";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import { JsonViewer } from "@/components/JsonViewer";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { imageUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { usePage } from "@/hooks/usePage";

export default function PageDetail({ params }: { params: Promise<{ id: string; n: string }> }) {
  const { id, n } = use(params);
  const pageNum = Number(n);
  const q = usePage(id, pageNum);

  if (q.isLoading) return <Skeleton className="h-96 w-full" />;
  if (q.isError || !q.data) return <p className="text-sm text-danger">Failed to load page.</p>;
  const { page, structured_json, raw_text } = q.data;

  return (
    <div className="flex flex-col gap-4">
      <Link href={`/documents/${id}`} className="inline-flex w-fit items-center gap-1 text-sm text-muted-fg hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />Document
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-lg font-semibold text-foreground">Page {page.page_num}</h1>
        <Badge tone="muted">{titleCase(page.page_type)}</Badge>
        <Badge tone={page.ocr_status === "done" ? "ok" : "warn"}>{page.ocr_status}</Badge>
        {page.language_detected && <Badge tone="info">{page.language_detected}</Badge>}
        {page.confidence_score != null && <span className="tnum text-xs text-muted-fg">conf {page.confidence_score.toFixed(0)}</span>}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden p-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imageUrl(id, pageNum)} alt={`Page ${pageNum}`} className="w-full" />
        </Card>
        <div className="flex flex-col gap-3">
          {page.page_summary && (
            <div className="rounded-lg border bg-card">
              <div className="border-b px-3 py-2 text-sm font-medium text-foreground">summary</div>
              <p className="px-3 py-2 text-sm text-muted-fg">{page.page_summary}</p>
            </div>
          )}
          <JsonViewer data={structured_json} />
          <div className="rounded-lg border bg-card">
            <div className="border-b px-3 py-2 text-sm font-medium text-foreground">raw_text</div>
            <pre className="max-h-[40vh] overflow-auto px-3 py-2 font-mono text-xs leading-relaxed text-foreground whitespace-pre-wrap">
              {raw_text ?? "—"}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
