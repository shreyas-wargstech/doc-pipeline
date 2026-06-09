import { describe, expect, it } from "vitest";
import { evalReducer, initialEvalState, type EvalPage } from "@/lib/eval-reducer";

const pages: EvalPage[] = [
  { page_id: "d:1", document_id: "d", page_num: 1, s3_key_image: "k1", label: null, height_cv: 0.1, stroke_cv: 0.1, n_components: 30 },
  { page_id: "d:2", document_id: "d", page_num: 2, s3_key_image: "k2", label: null, height_cv: 0.5, stroke_cv: 0.5, n_components: 30 },
];

describe("evalReducer", () => {
  it("loads pages and starts at cursor 0", () => {
    const s = evalReducer(initialEvalState, { type: "load", pages });
    expect(s.pages.length).toBe(2);
    expect(s.cursor).toBe(0);
  });

  it("applying a label advances the cursor and records the label locally", () => {
    let s = evalReducer(initialEvalState, { type: "load", pages });
    s = evalReducer(s, { type: "label", page_id: "d:1", label: "typed" });
    expect(s.pages[0].label).toBe("typed");
    expect(s.cursor).toBe(1);
  });

  it("does not advance past the last page", () => {
    let s = evalReducer(initialEvalState, { type: "load", pages });
    s = { ...s, cursor: 1 };
    s = evalReducer(s, { type: "label", page_id: "d:2", label: "handwritten" });
    expect(s.cursor).toBe(1);
  });

  it("skip advances without labeling", () => {
    let s = evalReducer(initialEvalState, { type: "load", pages });
    s = evalReducer(s, { type: "skip" });
    expect(s.cursor).toBe(1);
    expect(s.pages[0].label).toBeNull();
  });
});
