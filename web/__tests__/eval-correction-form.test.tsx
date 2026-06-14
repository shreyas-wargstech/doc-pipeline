import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EvalCorrectionForm } from "@/components/EvalCorrectionForm";
import type { DocFull } from "@/lib/types";

const mutateAsync = vi.fn().mockResolvedValue({
  doc: {}, match_result: { match_status: "matched", reference_data_id: 1, method: "exact", score: null, candidate_registration_no: "12345", matched_on: "registration_no+name" },
});

vi.mock("@/hooks/useEvalQueue", () => ({
  useCorrectDocument: () => ({ mutateAsync, isPending: false }),
}));

function makeDoc(overrides: Partial<DocFull> = {}): DocFull {
  return {
    document_id: "doc1", document_category: "practitioner", document_type: "registration",
    original_filename: "f.pdf", qr_content: null, s3_key_pdf: "k/f.pdf", page_count: 3,
    status: "manual_review", document_reference_no: "AMR-MCH-26-A-00001",
    application_no: null, registration_no: null, applicant_name_raw: "Jane Doe",
    dob: "1990-01-01", gender: "F", reference_data_id: null, match_status: "manual_review",
    document_summary: null, metadata: {}, created_at: "2026-06-14T00:00:00Z",
    updated_at: "2026-06-14T00:00:00Z",
    ...overrides,
  };
}

describe("EvalCorrectionForm", () => {
  it("renders the editable identity fields pre-filled from the document", () => {
    render(<EvalCorrectionForm doc={makeDoc()} />);
    expect(screen.getByLabelText(/applicant name/i)).toHaveValue("Jane Doe");
    expect(screen.getByLabelText(/registration no/i)).toHaveValue("");
  });

  it("submits only the changed fields and shows the new match status", async () => {
    const user = userEvent.setup();
    render(<EvalCorrectionForm doc={makeDoc()} />);
    await user.type(screen.getByLabelText(/registration no/i), "12345");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ registration_no: "12345" }));
    expect(await screen.findByText(/matched/i)).toBeInTheDocument();
  });
});
