import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import PageDetail from "@/app/(dash)/documents/[id]/pages/[n]/page";
import type { DocDetailResponse, PageDetailResponse } from "@/lib/types";

const push = vi.fn();
vi.mock("@/app/providers", () => ({ useToast: () => ({ toasts: [], push }) }));

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPush }) }));

if (!navigator.clipboard) {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn() },
    configurable: true,
  });
}
let writeText: MockInstance<(data: string) => Promise<void>>;

function makeDoc(overrides: Partial<DocDetailResponse["doc"]> = {}): DocDetailResponse {
  return {
    doc: {
      document_id: "doc1", document_category: "practitioner", document_type: null,
      original_filename: "f.pdf", qr_content: null, s3_key_pdf: "x", page_count: 3,
      status: "processed", document_reference_no: null, application_no: null,
      registration_no: "REG1", applicant_name_raw: null, dob: null, gender: null,
      reference_data_id: null, match_status: "matched", document_summary: null,
      metadata: {}, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
      bookmarked: false,
      ...overrides,
    },
    pages: [],
    ocr_done: 3,
    structured_done: 3,
  };
}

function makePageResponse(pageNum: number, overrides: Partial<PageDetailResponse["page"]> = {}): PageDetailResponse {
  return {
    page: {
      page_id: `p${pageNum}`, document_id: "doc1", page_num: pageNum,
      s3_key_image: "x", page_type: "form", raw_text: null, structured_json: null,
      confidence_score: 92, language_detected: "eng", page_summary: "A summary.",
      ocr_status: "done", created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
      ...overrides,
    },
    structured_json: { foo: "bar" },
    raw_text: "raw text body",
  };
}

vi.mock("@/hooks/useDocument", () => ({ useDocument: () => ({ data: makeDoc(), isLoading: false }) }));
vi.mock("@/hooks/usePage", () => ({
  usePage: (_id: string, pageNum: number) => ({ data: makePageResponse(pageNum), isLoading: false, isError: false }),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe("PageDetail viewer", () => {
  it("renders tabs and switches between summary/structured/raw", async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    wrap(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);

    expect(await screen.findByText("A summary.")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /structured/i }));
    expect(screen.getByText(/"foo"/)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /raw text/i }));
    expect(screen.getByText("raw text body")).toBeInTheDocument();
  });

  it("links to prev/next pages and disables at bounds", async () => {
    wrap(<PageDetail params={Promise.resolve({ id: "doc1", n: "1" })} />);
    expect(await screen.findByRole("link", { name: /previous page/i })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("link", { name: /next page/i })).toHaveAttribute("href", "/documents/doc1/pages/2");
  });

  it("copies the page link to clipboard", async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    wrap(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);
    await user.click(await screen.findByRole("button", { name: /copy link/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(push).toHaveBeenCalledWith("ok", expect.stringMatching(/copied/i));
  });
});
