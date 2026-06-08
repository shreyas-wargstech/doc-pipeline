"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { applyStreamEvent } from "@/lib/sse-reducer";
import type { DocumentsResponse, StreamEvent } from "@/lib/types";

/** Opens a single EventSource to /api/stream and patches every cached
 * documents query in place. Pauses while the tab is hidden; EventSource
 * auto-reconnects on drop. */
export function useDocumentStream() {
  const qc = useQueryClient();
  useEffect(() => {
    let es: EventSource | null = null;

    const open = () => {
      if (es || document.hidden) return;
      es = new EventSource("/api/stream", { withCredentials: true });
      es.onmessage = (e) => {
        let evt: StreamEvent;
        try { evt = JSON.parse(e.data) as StreamEvent; } catch { return; }
        qc.setQueriesData<DocumentsResponse>({ queryKey: ["documents"] }, (old) => applyStreamEvent(old, evt));
        // also nudge the open detail page to refetch its richer payload
        qc.invalidateQueries({ queryKey: ["document", evt.document_id] });
      };
      es.onerror = () => { es?.close(); es = null; }; // browser will reopen via our visibility handler / next mount
    };

    const onVis = () => { if (document.hidden) { es?.close(); es = null; } else open(); };

    open();
    document.addEventListener("visibilitychange", onVis);
    return () => { document.removeEventListener("visibilitychange", onVis); es?.close(); es = null; };
  }, [qc]);
}
