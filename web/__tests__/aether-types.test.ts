import { describe, it, expect } from "vitest";
import type { ToolResult } from "@/lib/types";

describe("ToolResult union", () => {
  it("narrows on kind", () => {
    const r: ToolResult = { kind: "narrative", document_id: "a", narrative: "hi" };
    if (r.kind === "narrative") expect(r.narrative).toBe("hi");
  });
  it("supports search hits", () => {
    const r: ToolResult = { kind: "search", hits: [], total: 0 };
    expect(r.total).toBe(0);
  });
});
