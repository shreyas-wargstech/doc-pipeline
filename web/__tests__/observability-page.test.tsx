import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ObservabilityPage from "@/app/(dash)/observability/page";
import type { AuditRow } from "@/lib/types";

const useMetrics = vi.fn();
const useAudit = vi.fn();
vi.mock("@/hooks/useMetrics", () => ({ useMetrics: () => useMetrics() }));
vi.mock("@/hooks/useAudit", () => ({ useAudit: (f: unknown) => useAudit(f) }));

function row(): AuditRow {
  return {
    id: 1, ts: new Date().toISOString(), username: "alice", action: "ingest",
    document_id: "doc-xyz-789", params: { a: 1 }, result: "ok", detail: "ran fine",
  };
}

const metricsOk = { data: { status_counts: { processed: 5, processing: 2 }, match_counts: { matched: 4 } }, isLoading: false, isError: false };

describe("ObservabilityPage", () => {
  it("renders the page heading and KPI overview", () => {
    useMetrics.mockReturnValue(metricsOk);
    useAudit.mockReturnValue({ data: { rows: [] }, isLoading: false, isError: false });
    render(<ObservabilityPage />);
    expect(screen.getByRole("heading", { level: 1, name: /observability/i })).toBeInTheDocument();
    expect(screen.getByText("Total")).toBeInTheDocument();
  });

  it("opens the detail drawer when an audit row is clicked", async () => {
    useMetrics.mockReturnValue(metricsOk);
    useAudit.mockReturnValue({ data: { rows: [row()] }, isLoading: false, isError: false });
    const user = userEvent.setup();
    render(<ObservabilityPage />);
    await user.click(screen.getByText("alice"));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(within(screen.getByRole("dialog")).getByText("ran fine")).toBeInTheDocument();
  });

  it("shows an error message when audit fails to load", () => {
    useMetrics.mockReturnValue(metricsOk);
    useAudit.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<ObservabilityPage />);
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  });
});
