import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DocumentDetail from "@/app/(dash)/documents/[id]/page";
import type { DocDetailResponse } from "@/lib/types";

vi.mock("@/app/action-bar", () => ({ useSetActionBar: () => {} }));
vi.mock("@/components/ActionButtons", () => ({ ActionButtons: () => <div /> }));
vi.mock("@/hooks/useBookmarks", () => ({ useToggleBookmark: () => ({ mutate: vi.fn() }) }));

const data = {
  doc: {
    document_id: "doc1", document_category: "practitioner", document_type: "application",
    original_filename: "scan.pdf", registration_no: "REG-12345", application_no: 9001,
    document_reference_no: "DR-7", applicant_name_raw: "Asha Patil", dob: "1990-01-02",
    status: "processed", match_status: "matched", page_count: 3,
    document_summary: "Bundle summary.", updated_at: "2026-06-14T00:00:00Z",
    bookmarked: false,
  },
  ocr_done: 3, structured_done: 3,
} as unknown as DocDetailResponse;

vi.mock("@/hooks/useDocument", () => ({ useDocument: () => ({ isLoading: false, isError: false, data }) }));

describe("DocumentDetail", () => {
  it("renders the registration number as the page heading", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(await screen.findByRole("heading", { level: 1, name: /REG-12345/ })).toBeInTheDocument();
  });

  it("renders a bookmark toggle", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(await screen.findByRole("button", { name: "Add bookmark" })).toBeInTheDocument();
  });

  it("shows metadata fields", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(await screen.findByText("Asha Patil")).toBeInTheDocument();
    expect(screen.getAllByText("REG-12345")).toHaveLength(2);
  });
});
