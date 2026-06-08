import { describe, expect, it } from "vitest";
import { applyStreamEvent } from "@/lib/sse-reducer";
import type { DocumentsResponse, StreamEvent } from "@/lib/types";

const base: DocumentsResponse = {
  documents: [
    { document_id: "a", document_category: "practitioner", document_type: null, status: "processing",
      match_status: null, page_count: 3, original_filename: "a.pdf", registration_no: "1",
      updated_at: "2026-06-08T00:00:00", ocr_done: 1, ocr_total: 3 },
  ],
  total: 1, offset: 0, limit: 50,
};

const evt: StreamEvent = { document_id: "a", status: "processed", match_status: "matched", ocr_done: 3, ocr_total: 3 };

describe("applyStreamEvent", () => {
  it("patches the matching row's live fields, leaves others intact", () => {
    const next = applyStreamEvent(base, evt);
    expect(next?.documents[0]).toMatchObject({ status: "processed", match_status: "matched", ocr_done: 3, original_filename: "a.pdf" });
  });
  it("returns the same object when the doc is not on the page (no-op)", () => {
    const next = applyStreamEvent(base, { ...evt, document_id: "zzz" });
    expect(next).toBe(base);
  });
  it("tolerates undefined cache (returns it unchanged)", () => {
    expect(applyStreamEvent(undefined, evt)).toBeUndefined();
  });
});
