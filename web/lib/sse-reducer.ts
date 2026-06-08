import type { DocumentsResponse, StreamEvent } from "@/lib/types";

/** Pure: return a new DocumentsResponse with the live fields of the matching
 * row patched from the SSE event. No-op (same reference) if the doc isn't on
 * the current page, or the cache is undefined. */
export function applyStreamEvent(
  cache: DocumentsResponse | undefined,
  evt: StreamEvent,
): DocumentsResponse | undefined {
  if (!cache) return cache;
  const idx = cache.documents.findIndex((d) => d.document_id === evt.document_id);
  if (idx === -1) return cache;
  const documents = cache.documents.slice();
  documents[idx] = {
    ...documents[idx],
    status: evt.status,
    match_status: evt.match_status,
    ocr_done: evt.ocr_done,
    ocr_total: evt.ocr_total,
  };
  return { ...cache, documents };
}
