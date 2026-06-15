"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
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
      setRun((prev) => (prev ? applyRunEvent(prev, evt) : applyRunEvent({} as RunState, evt)));
      if (evt.type === "done") closeStream();
    };
    es.onerror = () => { closeStream(); };
    esRef.current = es;
  }, [closeStream]);

  // On mount: recover any active (running/paused) run from the server so a
  // browser reload doesn't lose the live run. Only re-subscribe to SSE while
  // the run is actively progressing; a paused run is static until resumed.
  useEffect(() => {
    let cancelled = false;
    apiGet<RunState | null>("/api/pipelines/runs").then((active) => {
      if (cancelled || active == null) return;
      setRun(active);
      if (active.status === "running") subscribe(active.run_id);
    }).catch(() => { /* no active run / network error — start fresh */ });
    return () => { cancelled = true; };
  }, [subscribe]);

  useEffect(() => () => closeStream(), [closeStream]);

  const start = useCallback(async ({ folder, category, force }: StartArgs) => {
    setError(null);
    try {
      const { run_id, total } = await apiPost<{ run_id: string; total: number }>(
        "/api/pipelines/run", { folder, category, force });
      // Seed an optimistic shell; the SSE summary frame overwrites it.
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

  const pause = useCallback(async () => {
    if (!run) return;
    await apiPost(`/api/pipelines/run/${run.run_id}/pause`).catch(() => {});
  }, [run]);

  const resume = useCallback(async () => {
    if (!run) return;
    setError(null);
    try {
      const { run_id } = await apiPost<{ run_id: string; total: number }>(
        `/api/pipelines/run/${run.run_id}/resume`, {});
      setRun((prev) => (prev ? { ...prev, status: "running" } : prev));
      subscribe(run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to resume run");
    }
  }, [run, subscribe]);

  const isRunning = run?.status === "running";
  const isPaused = run?.status === "paused";
  return { run, error, start, cancel, pause, resume, isRunning, isPaused };
}
