"use client";
import { useRouter } from "next/navigation";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { fmtDateTime, titleCase } from "@/lib/format";
import type { EvalQueueRow } from "@/lib/types";

export function EvalQueueTable({ rows }: { rows: EvalQueueRow[] }) {
  const router = useRouter();

  if (rows.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
        <Typography color="text.secondary" variant="body2">No documents need review.</Typography>
      </Paper>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Applicant</TableCell>
            <TableCell>Reg. no</TableCell>
            <TableCell>DOB</TableCell>
            <TableCell>Type</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Match</TableCell>
            <TableCell>Updated</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow
              key={r.document_id}
              hover
              onClick={() => router.push(`/eval/${r.document_id}`)}
              sx={{ cursor: "pointer" }}
            >
              <TableCell>{r.applicant_name_raw ?? "—"}</TableCell>
              <TableCell sx={{ fontFamily: "var(--font-mono)" }}>{r.registration_no ?? "—"}</TableCell>
              <TableCell>{r.dob ?? "—"}</TableCell>
              <TableCell>{titleCase(r.document_type)}</TableCell>
              <TableCell><StatusBadge status={r.status} /></TableCell>
              <TableCell><MatchBadge status={r.match_status} /></TableCell>
              <TableCell className="tnum">
                <Typography variant="body2" color="text.secondary">{fmtDateTime(r.updated_at)}</Typography>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
