"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiPost } from "@/lib/api";
import { applyRunEvent, emptyRun } from "@/lib/pipeline-reducer";
import type { RunEvent, RunState } from "@/lib/types";

interface StartArgs { folder: string; category: string; force: boolean; }

export function useRunPipeline() {
  const [run, setRun] = useState<RunState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const closeStream = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const subscribe = useCallback((runId: string) => {
    closeStream();
    const es = new EventSource(`/api/pipelines/run/${runId}/events`, { withCredentials: true });
    es.onmessage = (e) => {
      let evt: RunEvent;
      try { evt = JSON.parse(e.data) as RunEvent; } catch { return; }
      setRun((prev) => (prev ? applyRunEvent(prev, evt) : prev));
      if (evt.type === "done") closeStream();
    };
    es.onerror = () => { closeStream(); };
    esRef.current = es;
  }, [closeStream]);

  const start = useCallback(async ({ folder, category, force }: StartArgs) => {
    setError(null);
    try {
      const { run_id, total } = await apiPost<{ run_id: string; total: number }>(
        "/api/pipelines/run", { folder, category, force });
      // Seed an optimistic shell; the SSE replay frame will overwrite it.
      setRun(emptyRun(run_id, folder, Array.from({ length: total }, () => "")));
      subscribe(run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to start run");
    }
  }, [subscribe]);

  const cancel = useCallback(async () => {
    if (!run) return;
    await apiPost(`/api/pipelines/run/${run.run_id}/cancel`).catch(() => {});
  }, [run]);

  useEffect(() => () => closeStream(), [closeStream]);

  const isRunning = run?.status === "running";
  return { run, error, start, cancel, isRunning };
}
