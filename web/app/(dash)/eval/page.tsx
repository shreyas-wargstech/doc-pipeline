"use client";
import { useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useEvalPages, useEnrol } from "@/hooks/useEval";
import { useEvalQueue } from "@/hooks/useEvalQueue";
import { EvalLabeler } from "@/components/EvalLabeler";
import { EvalScorePanel } from "@/components/EvalScorePanel";
import { EvalQueueTable } from "@/components/EvalQueueTable";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";

export default function EvalPage() {
  const [tab, setTab] = useState(0);
  const [docId, setDocId] = useState("");
  const queue = useEvalQueue();
  const pages = useEvalPages();
  const enrol = useEnrol();

  const tabs = [
    { label: "Review queue", index: 0 },
    { label: "Content-type lab", index: 1 },
  ];

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <PageHeader
        title="Evaluation"
        subtitle="Manual review queue and content-type labelling workspace."
      />

      <div className="flex gap-1 border-b border-border" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.index}
            role="tab"
            aria-selected={tab === t.index}
            onClick={() => setTab(t.index)}
            className={cn(
              "px-4 py-2 text-sm font-medium transition-colors",
              tab === t.index
                ? "border-b-2 border-primary text-primary"
                : "text-muted-fg hover:text-foreground"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 0 && (
        queue.isError ? (
          <p className="text-sm text-danger">Failed to load review queue.</p>
        ) : queue.data ? (
          <EvalQueueTable rows={queue.data.documents} />
        ) : (
          <Skeleton className="h-64 w-full" />
        )
      )}

      {tab === 1 && (
        <div className="flex flex-col gap-4 animate-fade-in">
          <div className="flex items-end gap-2">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-fg">document_id (blank = all pages)</label>
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
              <span className="self-center text-sm text-muted-fg">
                enrolled {enrol.data.enrolled ?? 0} page(s)
              </span>
            ) : null}
          </div>
          {pages.isError ? (
            <p className="text-sm text-danger">Failed to load eval pages: {String(pages.error)}</p>
          ) : pages.data ? (
            <EvalLabeler pages={pages.data.pages} />
          ) : (
            <Skeleton className="h-64 w-full" />
          )}
          <EvalScorePanel />
        </div>
      )}
    </div>
  );
}
