import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DetailPanel } from "@/components/retrieval/DetailPanel";
import type { SearchPagesResponse } from "@/lib/types";

const mockUse = vi.fn();
vi.mock("@/hooks/useSearch", () => ({
  useSearchDocPages: (id: string | null) => mockUse(id),
}));

function pages(over: Partial<SearchPagesResponse> = {}): SearchPagesResponse {
  return {
    document_id: "doc-abcdef123456",
    count: 1,
    hits: [
      {
        page_id: "doc:1",
        page_num: 1,
        page_type: "app_cover",
        s3_key_image: "x.png",
        page_summary: "Cover sheet for R-22020.",
        search_keywords: ["r-22020"],
        entities: [{ type: "PERSON", value: "Priya Kulkarni" }],
        index_status: "done",
      },
    ],
    ...over,
  };
}

describe("DetailPanel", () => {
  it("shows the empty state when no document is selected", () => {
    mockUse.mockReturnValue({ data: undefined, isLoading: false });
    render(<DetailPanel documentId={null} />);
    expect(screen.getByText(/select a result/i)).toBeInTheDocument();
  });

  it("renders pages and an Open-in-viewer link when populated", () => {
    mockUse.mockReturnValue({ data: pages(), isLoading: false });
    render(<DetailPanel documentId="doc-abcdef123456" />);
    expect(screen.getByText(/cover sheet for r-22020/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /open in viewer/i });
    expect(link).toHaveAttribute("href", "/documents/doc-abcdef123456");
  });
});
