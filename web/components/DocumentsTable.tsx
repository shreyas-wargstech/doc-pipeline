"use client";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
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
      <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
        <Typography color="text.secondary" variant="body2">{emptyText}</Typography>
      </Paper>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell padding="checkbox" />
            <TableCell>Reg / File</TableCell>
            <TableCell>Category</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Match</TableCell>
            <TableCell>OCR</TableCell>
            <TableCell>Updated</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow
              key={r.document_id}
              hover
              onClick={() => router.push(`/documents/${r.document_id}`)}
              sx={{ cursor: "pointer" }}
            >
              <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
                <BookmarkStar documentId={r.document_id} bookmarked={r.bookmarked} />
              </TableCell>
              <TableCell sx={{ fontFamily: "var(--font-mono)" }}>
                <Box sx={{ display: "flex", flexDirection: "column" }}>
                  <Typography variant="body2">{r.registration_no ?? "—"}</Typography>
                  <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: "18rem" }}>
                    {r.original_filename}
                  </Typography>
                </Box>
              </TableCell>
              <TableCell>{titleCase(r.document_category)}</TableCell>
              <TableCell><StatusBadge status={r.status} /></TableCell>
              <TableCell><MatchBadge status={r.match_status} /></TableCell>
              <TableCell><ProgressBar done={r.ocr_done} total={r.ocr_total} /></TableCell>
              <TableCell className="tnum"><Typography variant="body2" color="text.secondary">{fmtDateTime(r.updated_at)}</Typography></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
