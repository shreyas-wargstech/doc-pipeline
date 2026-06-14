import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EvalDetailPage from "@/app/(dash)/eval/[id]/page";
import type { DocDetailResponse } from "@/lib/types";

function makeData(): DocDetailResponse {
  return {
    doc: {
      document_id: "doc1", document_category: "practitioner", document_type: "registration",
      original_filename: "f.pdf", qr_content: null, s3_key_pdf: "k/f.pdf", page_count: 1,
      status: "manual_review", document_reference_no: "AMR-MCH-26-A-00001",
      application_no: null, registration_no: null, applicant_name_raw: "Jane Doe",
      dob: "1990-01-01", gender: "F", reference_data_id: null, match_status: "manual_review",
      document_summary: null, metadata: {}, created_at: "2026-06-14T00:00:00Z",
      updated_at: "2026-06-14T00:00:00Z",
    },
    pages: [{
      page_id: "doc1:1", document_id: "doc1", page_num: 1, s3_key_image: "k/p1.png",
      page_type: "application_form", raw_text: null, structured_json: null,
      confidence_score: null, language_detected: null, page_summary: null,
      ocr_status: "done", created_at: "2026-06-14T00:00:00Z", updated_at: "2026-06-14T00:00:00Z",
    }],
    ocr_done: 1, structured_done: 1,
  };
}

vi.mock("@/hooks/useDocument", () => ({
  useDocument: () => ({ data: makeData(), isLoading: false, isError: false }),
}));
vi.mock("@/hooks/useEvalQueue", () => ({
  useCorrectDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

describe("EvalDetailPage", () => {
  it("shows the source page image and the correction form", async () => {
    render(<EvalDetailPage params={Promise.resolve({ id: "doc1" })} />);
    expect(await screen.findByLabelText(/applicant name/i)).toHaveValue("Jane Doe");
    expect(screen.getByRole("img", { name: /page 1/i })).toBeInTheDocument();
  });
});
