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
      original_filename: "f.pdf", qr_content: null, s3_key_pdf: "x", page_count: 2,
      status: "processed", document_reference_no: "DR1", application_no: 123,
      registration_no: "REG1", applicant_name_raw: "Jane Doe", dob: "1990-01-01", gender: "F",
      reference_data_id: 1, match_status: "matched", document_summary: "A summary.",
      metadata: {}, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    },
    pages: [],
    ocr_done: 2,
    structured_done: 2,
  };
}

vi.mock("@/hooks/useDocument", () => ({ useDocument: () => ({ data: makeDoc(), isLoading: false, isError: false }) }));

describe("DocumentDetail overview", () => {
  it("publishes ActionButtons to the action bar instead of rendering them inline", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    await screen.findByText("REG1");
    expect(setActionBar).toHaveBeenCalled();
    const node = setActionBar.mock.calls.at(-1)?.[0] as React.ReactElement<{ documentId: string }>;
    expect(node.props.documentId).toBe("doc1");
    expect(screen.queryByTestId("action-buttons")).not.toBeInTheDocument();
  });

  it("does not render a page grid (superseded by the page rail)", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    await screen.findByText("REG1");
    expect(screen.queryByText(/page 1/i)).not.toBeInTheDocument();
  });

  it("still renders document metadata", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(await screen.findByText("REG1")).toBeInTheDocument();
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
  });
});
