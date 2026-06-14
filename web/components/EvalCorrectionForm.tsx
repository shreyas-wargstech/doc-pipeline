"use client";
import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { useCorrectDocument } from "@/hooks/useEvalQueue";
import { useToastSafe } from "@/app/providers";
import type { CorrectionPatch, DocFull, MatchResultOut, MatchStatus } from "@/lib/types";

const FIELDS: { key: keyof CorrectionPatch; label: string; docKey: keyof DocFull }[] = [
  { key: "applicant_name_raw", label: "Applicant name", docKey: "applicant_name_raw" },
  { key: "registration_no", label: "Registration no", docKey: "registration_no" },
  { key: "dob", label: "Date of birth", docKey: "dob" },
  { key: "gender", label: "Gender", docKey: "gender" },
  { key: "application_no", label: "Application no", docKey: "application_no" },
  { key: "document_reference_no", label: "Document reference no", docKey: "document_reference_no" },
];

function toFieldValue(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

export function EvalCorrectionForm({ doc }: { doc: DocFull }) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(FIELDS.map((f) => [f.key, toFieldValue(doc[f.docKey])])),
  );
  const [matchResult, setMatchResult] = useState<MatchResultOut | null>(null);
  const [matchStatus, setMatchStatus] = useState<MatchStatus>(doc.match_status);
  const correct = useCorrectDocument(doc.document_id);
  const pushToast = useToastSafe();

  async function onSave() {
    const patch: CorrectionPatch = {};
    for (const f of FIELDS) {
      const original = toFieldValue(doc[f.docKey]);
      const next = values[f.key] ?? "";
      if (next === original) continue;
      if (f.key === "application_no") {
        patch[f.key] = next === "" ? null : Number(next);
      } else {
        patch[f.key] = next === "" ? null : next;
      }
    }
    if (Object.keys(patch).length === 0) {
      pushToast("ok", "No changes to save.");
      return;
    }
    try {
      const res = await correct.mutateAsync(patch);
      setMatchResult(res.match_result);
      setMatchStatus(res.match_result.match_status);
      pushToast("ok", "Correction saved.");
    } catch (err) {
      pushToast("error", `Save failed: ${String(err)}`);
    }
  }

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography variant="subtitle2">Match status:</Typography>
        <MatchBadge status={matchStatus} />
        {matchResult?.matched_on && (
          <Typography variant="caption" color="text.secondary">via {matchResult.matched_on}</Typography>
        )}
      </Box>
      {FIELDS.map((f) => (
        <TextField
          key={f.key}
          label={f.label}
          value={values[f.key] ?? ""}
          onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
          size="small"
          fullWidth
          type={f.key === "dob" ? "date" : f.key === "application_no" ? "number" : "text"}
          slotProps={f.key === "dob" ? { inputLabel: { shrink: true } } : undefined}
        />
      ))}
      <Button variant="contained" onClick={onSave} disabled={correct.isPending}>
        {correct.isPending ? "Saving…" : "Save"}
      </Button>
    </Stack>
  );
}
