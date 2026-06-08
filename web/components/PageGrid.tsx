"use client";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { imageUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { OcrStatus, PageRow } from "@/lib/types";

const ocrTone: Record<OcrStatus, "ok" | "warn" | "danger" | "info" | "muted"> = {
  done: "ok", queued: "warn", pending: "muted", failed: "danger", skipped: "info",
};

export function PageGrid({ documentId, pages }: { documentId: string; pages: PageRow[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {pages.map((p) => (
        <Link key={p.page_id} href={`/documents/${documentId}/pages/${p.page_num}`}
          className="group flex flex-col overflow-hidden rounded-lg border bg-card transition-colors duration-150 hover:border-primary">
          <div className="aspect-[3/4] overflow-hidden bg-muted">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imageUrl(documentId, p.page_num)} alt={`Page ${p.page_num}`} loading="lazy"
              className="h-full w-full object-cover" />
          </div>
          <div className="flex items-center justify-between gap-1 p-2">
            <span className="tnum text-xs text-muted-fg">p.{p.page_num} · {titleCase(p.page_type)}</span>
            <Badge tone={ocrTone[p.ocr_status]}>{p.ocr_status}</Badge>
          </div>
        </Link>
      ))}
    </div>
  );
}
