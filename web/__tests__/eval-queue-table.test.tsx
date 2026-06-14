import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EvalQueueTable } from "@/components/EvalQueueTable";
import type { EvalQueueRow } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

function makeRow(overrides: Partial<EvalQueueRow> = {}): EvalQueueRow {
  return {
    document_id: "doc1", document_type: "registration",
    applicant_name_raw: "Jane Doe", registration_no: "12345",
    application_no: null, document_reference_no: "AMR-MCH-26-A-00001",
    dob: "1990-01-01", gender: "F",
    status: "manual_review", match_status: null,
    updated_at: "2026-06-14T00:00:00Z",
    ...overrides,
  };
}

describe("EvalQueueTable", () => {
  it("renders a row per document with key fields", () => {
    render(<EvalQueueTable rows={[makeRow()]} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("12345")).toBeInTheDocument();
  });

  it("shows an empty state when there are no rows", () => {
    render(<EvalQueueTable rows={[]} />);
    expect(screen.getByText(/no documents need review/i)).toBeInTheDocument();
  });

  it("navigates to the record detail on row click", async () => {
    const user = userEvent.setup();
    render(<EvalQueueTable rows={[makeRow()]} />);
    await user.click(screen.getByText("Jane Doe"));
    expect(push).toHaveBeenCalledWith("/eval/doc1");
  });
});
