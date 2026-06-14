"use client";
import { Drawer } from "@/components/ui/Drawer";
import { Badge } from "@/components/ui/Badge";
import { JsonViewer } from "@/components/JsonViewer";
import { fmtDateTime } from "@/lib/format";
import type { AuditRow } from "@/lib/types";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-muted-fg">{label}</span>
      <div className="text-sm text-foreground">{children}</div>
    </div>
  );
}

export function AuditDetailDrawer({ row, onClose }: { row: AuditRow | null; onClose: () => void }) {
  if (!row) return null;
  return (
    <Drawer open title="Event detail" onClose={onClose}>
      <Field label="When">{fmtDateTime(row.ts)}</Field>
      <Field label="User">{row.username}</Field>
      <Field label="Action"><span className="font-mono text-xs">{row.action}</span></Field>
      <Field label="Result">
        <Badge tone={row.result === "ok" ? "ok" : "danger"}>{row.result}</Badge>
      </Field>
      <Field label="Document">
        {row.document_id ? (
          <a href={`/documents/${row.document_id}`} className="font-mono text-xs text-primary hover:underline">
            {row.document_id}
          </a>
        ) : (
          <span className="text-muted-fg">—</span>
        )}
      </Field>
      {row.detail && <Field label="Detail">{row.detail}</Field>}
      <JsonViewer data={row.params} title="params" />
    </Drawer>
  );
}
