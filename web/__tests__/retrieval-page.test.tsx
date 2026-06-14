import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import RetrievalPage from "@/app/(dash)/retrieval/page";
import type { RetrievalHit } from "@/lib/types";

const useSearch = vi.fn();
const useSearchDocPages = vi.fn();
vi.mock("@/hooks/useSearch", () => ({
  useSearch: (q: string) => useSearch(q),
  useSearchDocPages: (id: string | null) => useSearchDocPages(id),
}));

function hit(): RetrievalHit {
  return {
    document_id: "doc-abc12345",
    s3_key_pdf: "x.pdf",
    document_type: "practitioner_application",
    score: 0.9,
    tier: 1,
    why_matched: "keyword match: renewal",
  };
}

describe("RetrievalPage", () => {
  it("shows the empty prompt before any search", () => {
    useSearch.mockReturnValue({ data: undefined, isLoading: false });
    useSearchDocPages.mockReturnValue({ data: undefined, isLoading: false });
    render(<RetrievalPage />);
    expect(screen.getByText(/enter a query to search/i)).toBeInTheDocument();
    expect(screen.getByText(/select a result/i)).toBeInTheDocument();
  });

  it("renders result cards after a search returns hits", async () => {
    useSearch.mockReturnValue({ data: { count: 1, hits: [hit()] }, isLoading: false });
    useSearchDocPages.mockReturnValue({ data: undefined, isLoading: false });
    const user = userEvent.setup();
    render(<RetrievalPage />);
    await user.type(screen.getByLabelText(/search query/i), "renewal");
    await user.click(screen.getByRole("button", { name: /^search$/i }));
    expect(screen.getByText(/keyword match: renewal/i)).toBeInTheDocument();
  });
});
