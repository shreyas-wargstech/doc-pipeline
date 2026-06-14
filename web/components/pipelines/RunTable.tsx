import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import type { RunItem } from "@/lib/types";

const STAGES = ["ingest", "ocr", "structure", "match", "persist", "index"];

function statusTone(s: RunItem["status"]): "ok" | "warn" | "danger" | "info" | "muted" {
  switch (s) {
    case "done": return "ok";
    case "failed": return "danger";
    case "running": return "info";
    default: return "muted";
  }
}

export function RunTable({ items }: { items: RunItem[] }) {
  return (
    <Table<RunItem>
      rows={items}
      rowKey={(it) => it.filename}
      empty="No items yet."
      columns={[
        { key: "filename", header: "File" },
        {
          key: "document_id",
          header: "Document",
          render: (it) => it.document_id
            ? (
              <Link href={`/documents/${it.document_id}`} className="font-mono text-primary hover:underline">
                {it.document_id.slice(0, 12)}…
              </Link>
            )
            : "—",
        },
        {
          key: "stage",
          header: "Stage",
          render: (it) => it.status === "running" && it.stage
            ? `${STAGES.indexOf(it.stage) + 1}/${STAGES.length} ${it.stage}`
            : "—",
        },
        {
          key: "status",
          header: "Result",
          render: (it) => it.status === "failed" && it.error
            ? <span title={it.error}><Badge tone="danger">failed</Badge></span>
            : <Badge tone={statusTone(it.status)}>{it.status}</Badge>,
        },
      ]}
    />
  );
}
