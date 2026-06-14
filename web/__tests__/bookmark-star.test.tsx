import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { BookmarkStar } from "@/components/BookmarkStar";

const mutate = vi.fn();
vi.mock("@/hooks/useBookmarks", () => ({
  useToggleBookmark: () => ({ mutate }),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("BookmarkStar", () => {
  beforeEach(() => mutate.mockReset());

  it("labels itself by state", () => {
    wrap(<BookmarkStar documentId="d1" bookmarked={false} />);
    expect(screen.getByRole("button", { name: "Add bookmark" })).toBeInTheDocument();
  });

  it("flips and fires the mutation with the next value on click", async () => {
    const user = userEvent.setup();
    wrap(<BookmarkStar documentId="d1" bookmarked={false} />);
    await user.click(screen.getByRole("button", { name: "Add bookmark" }));
    expect(mutate).toHaveBeenCalledWith(true, expect.objectContaining({ onError: expect.any(Function) }));
    expect(screen.getByRole("button", { name: "Remove bookmark" })).toBeInTheDocument();
  });
});
