import { describe, expect, it } from "vitest";
import { applyRunEvent, emptyRun } from "./pipeline-reducer";
import type { RunState } from "./types";

const base: RunState = {
  run_id: "r1", folder: "/x", category: "practitioner", force: false,
  status: "running", total: 2, done: 0, skipped: 0, failed: 0, running: 0,
  items: [
    { filename: "a.pdf", status: "pending", document_id: null, stage: null, error: null },
    { filename: "b.pdf", status: "pending", document_id: null, stage: null, error: null },
  ],
};

describe("applyRunEvent", () => {
  it("updates a single item on an item frame", () => {
    const next = applyRunEvent(base, {
      type: "item", filename: "a.pdf", status: "running", stage: "ocr",
      document_id: "doc-a",
    });
    expect(next.items[0].status).toBe("running");
    expect(next.items[0].stage).toBe("ocr");
    expect(next.items[0].document_id).toBe("doc-a");
    expect(next.items[1].status).toBe("pending"); // untouched
  });

  it("replaces summary counts on a summary frame", () => {
    const next = applyRunEvent(base, { type: "summary", done: 1, running: 1 } as never);
    expect(next.done).toBe(1);
    expect(next.running).toBe(1);
  });

  it("sets status on a done frame", () => {
    const next = applyRunEvent(base, { type: "done", status: "completed" } as never);
    expect(next.status).toBe("completed");
  });

  it("emptyRun produces a running shell", () => {
    const r = emptyRun("r2", "/y", ["a.pdf"]);
    expect(r.run_id).toBe("r2");
    expect(r.items).toHaveLength(1);
    expect(r.status).toBe("running");
  });
});
