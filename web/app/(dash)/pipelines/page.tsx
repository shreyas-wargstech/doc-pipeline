"use client";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { RunForm } from "@/components/pipelines/RunForm";
import { RunSummary } from "@/components/pipelines/RunSummary";
import { RunTable } from "@/components/pipelines/RunTable";
import { useRunPipeline } from "@/hooks/useRunPipeline";

export default function PipelinesPage() {
  const { run, error, start, cancel, isRunning } = useRunPipeline();

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Pipelines"
        subtitle="Run a folder of PDFs through the full pipeline, one document at a time."
      />
      {error && <p className="text-sm text-danger">{error}</p>}
      <RunForm onRun={start} disabled={isRunning} />
      {run && (
        <Card className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-4">
            <RunSummary run={run} />
            {isRunning && (
              <Button variant="destructive" onClick={cancel}>
                Cancel
              </Button>
            )}
          </div>
          <RunTable items={run.items} />
        </Card>
      )}
    </div>
  );
}
