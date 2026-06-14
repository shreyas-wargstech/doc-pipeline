import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DocumentDetail from "@/app/(dash)/documents/[id]/page";
import type { DocDetailResponse } from "@/lib/types";

const setActionBar = vi.fn();
vi.mock("@/app/action-bar", () => ({ useSetActionBar: (node: React.ReactNode) => setActionBar(node) }));
vi.mock("@/components/ActionButtons", () => ({ ActionButtons: ({ documentId }: { documentId: string }) => <div data-testid="action-buttons">{documentId}</div> }));

function makeDoc(): DocDetailResponse {
  return {
    doc: {
      document_id: "doc1", document_category: "practitioner", document_type: "registration",
      original_filename: "f.pdf", page_count: 2,
      status: "processed", document_reference_no: "DR1", application_no: 123,
      registration_no: "REG1", applicant_name_raw: "Jane Doe", dob: "1990-01-01",
      match_status: "matched", document_summary: "A summary.",
      created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    } as any,
    pages: [],
    ocr_done: 2,
    structured_done: 2,
  };
}

vi.mock("@/hooks/useDocument", () => ({ useDocument: () => ({ data: makeDoc(), isLoading: false, isError: false }) }));

describe("DocumentDetail overview", () => {
  it("publishes ActionButtons to the action bar instead of rendering them inline", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    await screen.findAllByText("REG1");
    expect(setActionBar).toHaveBeenCalled();
    const node = setActionBar.mock.calls.at(-1)?.[0] as React.ReactElement<{ documentId: string }>;
    expect(node.props.documentId).toBe("doc1");
    expect(screen.queryByTestId("action-buttons")).not.toBeInTheDocument();
  });

  it("does not render a page grid (superseded by the page rail)", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    await screen.findAllByText("REG1");
    expect(screen.queryByText(/page 1/i)).not.toBeInTheDocument();
  });

  it("still renders document metadata", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(await screen.findAllByText("REG1")).toHaveLength(2);
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
  });
});
