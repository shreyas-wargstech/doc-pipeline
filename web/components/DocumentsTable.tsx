"use client";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { BookmarkStar } from "@/components/BookmarkStar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { fmtDateTime, titleCase } from "@/lib/format";
import type { DocRow } from "@/lib/types";

export function DocumentsTable({
  rows,
  emptyText = "No documents match these filters.",
}: {
  rows: DocRow[];
  emptyText?: string;
}) {
  const router = useRouter();

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-border p-8 text-center">
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-3 py-2 font-medium w-10"></th>
            <th className="px-3 py-2 font-medium">Reg / File</th>
            <th className="px-3 py-2 font-medium">Category</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Match</th>
            <th className="px-3 py-2 font-medium">OCR</th>
            <th className="px-3 py-2 font-medium">Updated</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <motion.tr
              key={r.document_id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              onClick={() => router.push(`/documents/${r.document_id}`)}
              className="border-b last:border-0 transition-colors duration-150 hover:bg-surface-hover cursor-pointer"
            >
              <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                <BookmarkStar documentId={r.document_id} bookmarked={r.bookmarked} />
              </td>
              <td className="px-3 py-2 font-mono">
                <div className="flex flex-col">
                  <span className="text-foreground">{r.registration_no ?? "—"}</span>
                  <span className="max-w-[18rem] truncate text-xs text-muted-foreground">
                    {r.original_filename}
                  </span>
                </div>
              </td>
              <td className="px-3 py-2">{titleCase(r.document_category)}</td>
              <td className="px-3 py-2"><StatusBadge status={r.status} /></td>
              <td className="px-3 py-2"><MatchBadge status={r.match_status} /></td>
              <td className="px-3 py-2"><ProgressBar done={r.ocr_done} total={r.ocr_total} /></td>
              <td className="px-3 py-2 tnum">
                <span className="text-sm text-muted-foreground">{fmtDateTime(r.updated_at)}</span>
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
