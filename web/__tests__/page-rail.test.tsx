import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PageRail } from "@/components/PageRail";
import type { PageRow } from "@/lib/types";

vi.mock("next/navigation", () => ({ usePathname: () => "/documents/doc1/pages/2" }));

function makePage(overrides: Partial<PageRow>): PageRow {
  return {
    page_id: "p1",
    document_id: "doc1",
    page_num: 1,
    s3_key_image: "documents/doc1/pages/page_001.png",
    page_type: "cover",
    raw_text: null,
    structured_json: null,
    confidence_score: null,
    language_detected: null,
    page_summary: null,
    ocr_status: "done",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

const pages: PageRow[] = [
  makePage({ page_id: "p1", page_num: 1, page_type: "cover", ocr_status: "done" }),
  makePage({ page_id: "p2", page_num: 2, page_type: "application_form", ocr_status: "queued" }),
];

describe("PageRail", () => {
  it("renders a link per page with page number and type", () => {
    render(<PageRail documentId="doc1" pages={pages} />);
    expect(screen.getByRole("link", { name: /page 1/i })).toHaveAttribute("href", "/documents/doc1/pages/1");
    expect(screen.getByRole("link", { name: /page 2/i })).toHaveAttribute("href", "/documents/doc1/pages/2");
    expect(screen.getByText(/application form/i)).toBeInTheDocument();
  });

  it("marks the page matching the current pathname as active", () => {
    render(<PageRail documentId="doc1" pages={pages} />);
    expect(screen.getByRole("link", { name: /page 2/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /page 1/i })).not.toHaveAttribute("aria-current");
  });
});
