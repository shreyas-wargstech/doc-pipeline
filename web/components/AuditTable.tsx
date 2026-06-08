"use client";
import { Table, type Column } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { fmtDateTime } from "@/lib/format";
import type { AuditRow } from "@/lib/types";

export function AuditTable({ rows }: { rows: AuditRow[] }) {
  const columns: Column<AuditRow>[] = [
    { key: "ts", header: "When", className: "tnum text-muted-fg", render: (r) => fmtDateTime(r.ts) },
    { key: "username", header: "User" },
    { key: "action", header: "Action", render: (r) => <span className="font-mono text-xs">{r.action}</span> },
    { key: "document_id", header: "Document", className: "font-mono text-xs",
      render: (r) => (r.document_id ? `${r.document_id.slice(0, 10)}…` : "—") },
    { key: "result", header: "Result", render: (r) => <Badge tone={r.result === "ok" ? "ok" : "danger"}>{r.result}</Badge> },
    { key: "detail", header: "Detail", className: "max-w-[20rem] truncate text-muted-fg", render: (r) => r.detail ?? "—" },
  ];
  return <Table columns={columns} rows={rows} rowKey={(r) => String(r.id)} empty="No audit entries." />;
}
