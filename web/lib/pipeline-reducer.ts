import type { RunEvent, RunItem, RunState } from "./types";

export function emptyRun(runId: string, folder: string, filenames: string[]): RunState {
  return {
    run_id: runId, folder, category: "practitioner", force: false,
    status: "running", total: filenames.length, done: 0, skipped: 0, failed: 0, running: 0,
    items: filenames.map((filename) => ({
      filename, status: "pending", document_id: null, stage: null, error: null,
    })),
  };
}

/** Pure: returns a new RunState with the event applied. */
export function applyRunEvent(run: RunState, evt: RunEvent): RunState {
  if (evt.type === "item" && evt.filename) {
    const items = run.items.map((it): RunItem =>
      it.filename === evt.filename
        ? {
            ...it,
            status: (evt.status as RunItem["status"]) ?? it.status,
            stage: evt.stage !== undefined ? (evt.stage as string | null) : it.stage,
            document_id: evt.document_id !== undefined
              ? (evt.document_id as string | null) : it.document_id,
            error: evt.error !== undefined ? (evt.error as string | null) : it.error,
          }
        : it,
    );
    return { ...run, items };
  }
  // summary / done frames carry the full RunState shape — merge all fields except type.
  const { type, ...rest } = evt as Record<string, unknown>;
  void type;
  return { ...run, ...(rest as Partial<RunState>) };
}
