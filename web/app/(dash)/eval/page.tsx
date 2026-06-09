"use client";
import { useState } from "react";
import { useEvalPages, useEnrol } from "@/hooks/useEval";
import { EvalLabeler } from "@/components/EvalLabeler";
import { EvalScorePanel } from "@/components/EvalScorePanel";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function EvalPage() {
  const [docId, setDocId] = useState("");
  const pages = useEvalPages();
  const enrol = useEnrol();

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Content-type eval lab</h1>
      <div className="flex items-end gap-2">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">document_id (blank = all pages)</label>
          <Input
            value={docId}
            onChange={(e) => setDocId(e.target.value)}
            placeholder="document_id"
          />
        </div>
        <Button
          disabled={enrol.isPending}
          onClick={() => enrol.mutate(docId.trim() ? docId.trim() : null)}
        >
          {enrol.isPending ? "Enrolling…" : "Enrol"}
        </Button>
        {enrol.data ? (
          <span className="self-center text-sm text-muted-foreground">
            enrolled {enrol.data.enrolled ?? 0} page(s)
          </span>
        ) : null}
      </div>
      {pages.data ? <EvalLabeler pages={pages.data.pages} /> : <p className="text-sm">Loading…</p>}
      <EvalScorePanel />
    </div>
  );
}
