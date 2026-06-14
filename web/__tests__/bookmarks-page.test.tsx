import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect } from "vitest";
import BookmarksPage from "@/app/(dash)/bookmarks/page";

vi.mock("@/hooks/useBookmarks", () => ({ useToggleBookmark: () => ({ mutate: vi.fn() }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const useDocuments = vi.fn();
vi.mock("@/hooks/useDocuments", () => ({ useDocuments: (f: unknown) => useDocuments(f) }));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("BookmarksPage", () => {
  it("requests only bookmarked documents", () => {
    useDocuments.mockReturnValue({ isLoading: false, isError: false, data: { documents: [], total: 0 } });
    wrap(<BookmarksPage />);
    expect(useDocuments).toHaveBeenCalledWith({ bookmarked: true });
  });

  it("shows an empty state when there are no bookmarks", () => {
    useDocuments.mockReturnValue({ isLoading: false, isError: false, data: { documents: [], total: 0 } });
    wrap(<BookmarksPage />);
    expect(screen.getByText("No bookmarks yet.")).toBeInTheDocument();
  });
});
