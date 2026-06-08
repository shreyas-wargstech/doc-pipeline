import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionButtons } from "@/components/ActionButtons";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

vi.mock("@/app/providers", async () => ({ useToast: () => ({ toasts: [], push: vi.fn() }) }));

describe("ActionButtons", () => {
  it("renders the three control actions", () => {
    wrap(<ActionButtons documentId="abc" />);
    expect(screen.getByRole("button", { name: /re-ingest/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /requeue ocr/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /re-classify/i })).toBeInTheDocument();
  });

  it("opens a confirm dialog before re-ingest (destructive guard)", async () => {
    const user = (await import("@testing-library/user-event")).default;
    wrap(<ActionButtons documentId="abc" />);
    await user.click(screen.getByRole("button", { name: /re-ingest/i }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
  });
});
