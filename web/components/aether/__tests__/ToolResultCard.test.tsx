import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolResultCard } from "@/components/aether/ToolResultCard";
import type { ToolResult } from "@/lib/types";

describe("ToolResultCard", () => {
  it("renders a fallback for an unknown kind", () => {
    const r = { kind: "totally-new", foo: 1 } as unknown as ToolResult;
    render(<ToolResultCard result={r} />);
    expect(screen.getByTestId("tool-result-fallback")).toBeInTheDocument();
  });
});
