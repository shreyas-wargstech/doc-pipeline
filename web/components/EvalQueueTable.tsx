"use client";
import { useRouter } from "next/navigation";
import { Table } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { fmtDateTime, titleCase } from "@/lib/format";
import type { EvalQueueRow } from "@/lib/types";

export function EvalQueueTable({ rows }: { rows: EvalQueueRow[] }) {
  const router = useRouter();

  if (rows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-panel border border-border bg-surface p-8 text-center">
        <p className="text-sm text-muted-fg">No documents need review.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-fg">
            <th className="px-3 py-2 font-medium">Applicant</th>
            <th className="px-3 py-2 font-medium">Reg. no</th>
            <th className="px-3 py-2 font-medium">DOB</th>
            <th className="px-3 py-2 font-medium">Type</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Match</th>
            <th className="px-3 py-2 font-medium">Updated</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.document_id}
              onClick={() => router.push(`/eval/${r.document_id}`)}
              className="border-b last:border-0 transition-colors duration-150 hover:bg-muted/40 cursor-pointer"
            >
              <td className="px-3 py-2 align-middle">{r.applicant_name_raw ?? "—"}</td>
              <td className="px-3 py-2 align-middle font-mono text-xs">{r.registration_no ?? "—"}</td>
              <td className="px-3 py-2 align-middle">{r.dob ?? "—"}</td>
              <td className="px-3 py-2 align-middle">{titleCase(r.document_type)}</td>
              <td className="px-3 py-2 align-middle"><StatusBadge status={r.status} /></td>
              <td className="px-3 py-2 align-middle"><MatchBadge status={r.match_status} /></td>
              <td className="px-3 py-2 align-middle tnum text-xs text-muted-fg">{fmtDateTime(r.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
