"use client";
import { useRouter } from "next/navigation";
import { Table, type Column } from "@/components/ui/Table";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { fmtDateTime, titleCase } from "@/lib/format";
import type { DocRow } from "@/lib/types";

export function DocumentsTable({ rows }: { rows: DocRow[] }) {
  const router = useRouter();
  const columns: Column<DocRow>[] = [
    { key: "registration_no", header: "Reg / File", className: "font-mono",
      render: (r) => (
        <div className="flex flex-col">
          <span className="text-foreground">{r.registration_no ?? "—"}</span>
          <span className="max-w-[18rem] truncate text-xs text-muted-fg">{r.original_filename}</span>
        </div>
      ) },
    { key: "document_category", header: "Category", render: (r) => titleCase(r.document_category) },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "match_status", header: "Match", render: (r) => <MatchBadge status={r.match_status} /> },
    { key: "ocr", header: "OCR", render: (r) => <ProgressBar done={r.ocr_done} total={r.ocr_total} /> },
    { key: "updated_at", header: "Updated", className: "tnum text-muted-fg", render: (r) => fmtDateTime(r.updated_at) },
  ];
  return <Table columns={columns} rows={rows} rowKey={(r) => r.document_id}
    onRowClick={(r) => router.push(`/documents/${r.document_id}`)} empty="No documents match these filters." />;
}
