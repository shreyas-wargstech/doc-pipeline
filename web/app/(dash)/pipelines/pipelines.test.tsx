import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RunState } from "@/lib/types";

const mockHook = vi.fn();
vi.mock("@/hooks/useRunPipeline", () => ({ useRunPipeline: () => mockHook() }));

import PipelinesPage from "./page";

function makeRun(over: Partial<RunState> = {}): RunState {
  return {
    run_id: "r1",
    folder: "/x",
    category: "practitioner",
    force: false,
    status: "running",
    total: 2,
    done: 1,
    skipped: 0,
    failed: 1,
    running: 0,
    items: [
      { filename: "a.pdf", status: "done", document_id: "doc-aaaaaaaaaaaa", stage: null, error: null },
      { filename: "b.pdf", status: "failed", document_id: null, stage: null, error: "boom" },
    ],
    ...over,
  };
}

// The warm-editorial Badge wraps its label + count alongside an aria-hidden dot
// span, so "Done 1" is split across child text nodes. Match on the badge
// element's normalized textContent instead of a single text node.
function badgeText(label: string) {
  return (_content: string, el: Element | null) =>
    el?.tagName === "SPAN" && el.textContent?.replace(/\s+/g, " ").trim() === label;
}

describe("PipelinesPage", () => {
  it("renders the run form when no run is active", () => {
    mockHook.mockReturnValue({ run: null, error: null, start: vi.fn(), cancel: vi.fn(), isRunning: false });
    render(<PipelinesPage />);
    expect(screen.getByRole("button", { name: /Run folder/i })).toBeInTheDocument();
  });

  it("renders summary counts and per-document rows", () => {
    mockHook.mockReturnValue({ run: makeRun(), error: null, start: vi.fn(), cancel: vi.fn(), isRunning: true });
    render(<PipelinesPage />);
    expect(screen.getByText(badgeText("Total 2"))).toBeInTheDocument();
    expect(screen.getByText(badgeText("Done 1"))).toBeInTheDocument();
    expect(screen.getByText(badgeText("Failed 1"))).toBeInTheDocument();
    expect(screen.getByText("a.pdf")).toBeInTheDocument();
    expect(screen.getByText("b.pdf")).toBeInTheDocument();
  });

  it("shows the error alert", () => {
    mockHook.mockReturnValue({ run: null, error: "bad folder", start: vi.fn(), cancel: vi.fn(), isRunning: false });
    render(<PipelinesPage />);
    expect(screen.getByText("bad folder")).toBeInTheDocument();
  });
});
