"use client";
import { useState } from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { useEvalPages, useEnrol } from "@/hooks/useEval";
import { useEvalQueue } from "@/hooks/useEvalQueue";
import { EvalLabeler } from "@/components/EvalLabeler";
import { EvalScorePanel } from "@/components/EvalScorePanel";
import { EvalQueueTable } from "@/components/EvalQueueTable";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function EvalPage() {
  const [tab, setTab] = useState(0);
  const [docId, setDocId] = useState("");
  const queue = useEvalQueue();
  const pages = useEvalPages();
  const enrol = useEnrol();

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Typography variant="h6" component="h1">Evaluation</Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} aria-label="Evaluation sections">
        <Tab label="Review queue" />
        <Tab label="Content-type lab" />
      </Tabs>

      {tab === 0 && (
        queue.isError ? (
          <Typography color="error" variant="body2">Failed to load review queue.</Typography>
        ) : queue.data ? (
          <EvalQueueTable rows={queue.data.documents} />
        ) : (
          <Typography variant="body2">Loading…</Typography>
        )
      )}

      {tab === 1 && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
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
          {pages.isError ? (
            <p className="text-sm text-destructive">Failed to load eval pages: {String(pages.error)}</p>
          ) : pages.data ? (
            <EvalLabeler pages={pages.data.pages} />
          ) : (
            <p className="text-sm">Loading…</p>
          )}
          <EvalScorePanel />
        </Box>
      )}
    </Box>
  );
}
