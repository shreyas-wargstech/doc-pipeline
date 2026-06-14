import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CostSection } from "@/components/CostSection";
import { fmtUsd } from "@/lib/format";
import type { CostsResponse, CostEventsResponse } from "@/lib/types";

const useCosts = vi.fn();
const useCostEvents = vi.fn();
vi.mock("@/hooks/useCosts", () => ({
  useCosts: () => useCosts(),
  useCostEvents: (s?: string, l?: number) => useCostEvents(s, l),
}));

const costs: CostsResponse = {
  summary: { cost: 0.5, total_tokens: 1200, calls: 7, errors: 1 },
  by_stage: { ocr_vlm: { cost: 0.4, total_tokens: 900, calls: 3 } },
  by_model: { "google/gemini-2.5-flash": { cost: 0.5, total_tokens: 1200, calls: 7 } },
};
const events: CostEventsResponse = {
  rows: [{
    id: 1, ts: "2026-06-15T10:00:00Z", stage: "ocr_vlm", model: "google/gemini-2.5-flash",
    document_id: "doc-abc", page_num: 2, prompt_tokens: 100, completion_tokens: 20,
    total_tokens: 120, cost: 0.003, status: "ok", detail: null,
  }],
};

describe("fmtUsd", () => {
  it("uses 2 decimals normally and 4 for sub-cent values", () => {
    expect(fmtUsd(0.5)).toBe("$0.50");
    expect(fmtUsd(0.003)).toBe("$0.0030");
    expect(fmtUsd(null)).toBe("$0.00");
  });
});

describe("CostSection", () => {
  it("renders cost KPIs and the breakdown + recent calls", () => {
    useCosts.mockReturnValue({ data: costs, isLoading: false, isError: false });
    useCostEvents.mockReturnValue({ data: events, isLoading: false, isError: false });
    render(<CostSection />);
    expect(screen.getByText(/total spend/i)).toBeInTheDocument();
    expect(screen.getByText("$0.50")).toBeInTheDocument();      // total spend KPI
    expect(screen.getByText(/cost by stage/i)).toBeInTheDocument();
    expect(screen.getByText("doc-abc")).toBeInTheDocument();    // recent call row
  });

  it("renders a loading skeleton while costs load", () => {
    useCosts.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    useCostEvents.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { container } = render(<CostSection />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });
});
