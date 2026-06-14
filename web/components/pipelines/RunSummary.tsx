import { Badge } from "@/components/ui/Badge";
import type { RunState } from "@/lib/types";

export function RunSummary({ run }: { run: RunState }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge tone="muted">Total {run.total}</Badge>
      <Badge tone="info">Running {run.running}</Badge>
      <Badge tone="ok">Done {run.done}</Badge>
      <Badge tone="muted">Skipped {run.skipped}</Badge>
      <Badge tone="danger">Failed {run.failed}</Badge>
      <Badge tone={run.status === "completed" ? "ok" : "muted"}>{run.status}</Badge>
    </div>
  );
}
