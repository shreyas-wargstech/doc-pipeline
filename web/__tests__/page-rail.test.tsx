import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PageRail } from "@/components/PageRail";
import type { PageRow } from "@/lib/types";

vi.mock("next/navigation", () => ({ usePathname: () => "/documents/doc1/pages/2" }));

function makePage(n: number, type: string): PageRow {
  return {
    page_id: `doc1:${n}`,
    document_id: "doc1",
    page_num: n,
    s3_key_image: "",
    page_type: type,
    raw_text: null,
    structured_json: null,
    confidence_score: null,
    language_detected: null,
    page_summary: null,
    ocr_status: "done",
    created_at: "",
    updated_at: "",
  };
}

const pages = [makePage(1, "cover"), makePage(2, "application_form"), makePage(3, "receipt")];

describe("PageRail", () => {
  it("renders a flat list with a page count header and per-page titles", () => {
    render(<PageRail documentId="doc1" pages={pages} collapsed={false} />);
    expect(screen.getByText("Pages · 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /application form/i })).toBeInTheDocument();
  });

  it("marks the active page with aria-current", () => {
    render(<PageRail documentId="doc1" pages={pages} collapsed={false} />);
    expect(screen.getByRole("link", { name: /application form/i })).toHaveAttribute("aria-current", "page");
  });

  it("hides the count header and keeps clickable links when collapsed", () => {
    render(<PageRail documentId="doc1" pages={pages} collapsed={true} />);
    expect(screen.queryByText("Pages · 3")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(3);
  });
});
