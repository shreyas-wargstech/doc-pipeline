"use client";
import { useState } from "react";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
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
    <Card className="flex flex-col gap-4 p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-foreground">Match status:</span>
        <MatchBadge status={matchStatus} />
        {matchResult?.matched_on && (
          <span className="text-xs text-muted-fg">via {matchResult.matched_on}</span>
        )}
      </div>
      {FIELDS.map((f) => (
        <div key={f.key} className="flex flex-col gap-1">
          <label htmlFor={`field-${f.key}`} className="text-xs font-medium text-muted-fg">
            {f.label}
          </label>
          <Input
            id={`field-${f.key}`}
            value={values[f.key] ?? ""}
            onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
            type={f.key === "dob" ? "date" : f.key === "application_no" ? "number" : "text"}
          />
        </div>
      ))}
      <Button onClick={onSave} disabled={correct.isPending} className="self-start">
        {correct.isPending ? "Saving…" : "Save"}
      </Button>
    </Card>
  );
}
