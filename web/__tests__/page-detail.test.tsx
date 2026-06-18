import React from "react";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PageDetail from "@/app/(dash)/documents/[id]/pages/[n]/page";
import type { PageDetailResponse, DocDetailResponse } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/app/providers", () => ({ useToast: () => ({ push: vi.fn() }) }));
vi.mock("@/components/PageRailContext", () => ({
  PageRailToggle: () => <button aria-label="Show page list" />,
}));

const page: PageDetailResponse = {
  page: {
    page_id: "doc1:2", document_id: "doc1", page_num: 2, s3_key_image: "",
    page_type: "application_form", raw_text: null, structured_json: null,
    confidence_score: 87, language_detected: "mar+eng", page_summary: "A summary.",
    ocr_status: "done", created_at: "", updated_at: "",
  },
  structured_json: { registration_no: "REG-1" },
  raw_text: "raw text body",
};
const doc = { doc: { page_count: 3 }, pages: [] } as unknown as DocDetailResponse;
const mockDoc: { value: unknown } = { value: doc };

vi.mock("@/hooks/usePage", () => ({ usePage: () => ({ isLoading: false, isError: false, data: page }) }));
vi.mock("@/hooks/useDocument", () => ({ useDocument: () => ({ data: mockDoc.value }) }));
vi.mock("react-zoom-pan-pinch", () => ({
  TransformWrapper: ({ children }: { children: (api: { zoomIn: () => void; zoomOut: () => void; resetTransform: () => void }) => React.ReactNode }) =>
    <>{children({ zoomIn: vi.fn(), zoomOut: vi.fn(), resetTransform: vi.fn() })}</>,
  TransformComponent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe("PageDetail", () => {
  afterEach(() => {
    mockDoc.value = doc;
  });

  it("renders without crashing when the document payload has no doc", async () => {
    mockDoc.value = { pages: [] };
    render(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);
    expect(await screen.findByRole("heading", { name: /page 2/i })).toBeInTheDocument();
  });

  it("renders the page title and a data-panel toggle", async () => {
    render(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);
    expect(await screen.findByRole("heading", { name: /page 2/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hide data panel|show data panel/i })).toBeInTheDocument();
  });

  it("shows the summary tab content by default", async () => {
    render(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);
    expect(await screen.findByText("A summary.")).toBeInTheDocument();
  });

  it("renders zoom controls over the page image", async () => {
    render(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);
    expect(await screen.findByRole("button", { name: /zoom in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /zoom out/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /fit to width/i })).toBeInTheDocument();
  });
});
