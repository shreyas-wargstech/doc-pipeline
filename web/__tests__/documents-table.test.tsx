import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DocumentsTable } from "@/components/DocumentsTable";
import type { DocRow } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/hooks/useBookmarks", () => ({ useToggleBookmark: () => ({ mutate: vi.fn() }) }));

function makeRow(overrides: Partial<DocRow> = {}): DocRow {
  return {
    document_id: "doc1", document_category: "practitioner", document_type: "registration",
    status: "processed", match_status: "matched", page_count: 3,
    original_filename: "f.pdf", registration_no: "REG1",
    updated_at: "2026-06-01T00:00:00Z", ocr_done: 3, ocr_total: 3, bookmarked: false,
    ...overrides,
  };
}

describe("DocumentsTable", () => {
  it("renders a row per document with key fields", () => {
    render(<DocumentsTable rows={[makeRow()]} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("REG1")).toBeInTheDocument();
    expect(screen.getByText("f.pdf")).toBeInTheDocument();
  });

  it("shows an empty state when there are no rows", () => {
    render(<DocumentsTable rows={[]} />);
    expect(screen.getByText(/no documents/i)).toBeInTheDocument();
  });

  it("navigates to the document on row click", async () => {
    const user = userEvent.setup();
    render(<DocumentsTable rows={[makeRow()]} />);
    await user.click(screen.getByText("REG1"));
    expect(push).toHaveBeenCalledWith("/documents/doc1");
  });
});
