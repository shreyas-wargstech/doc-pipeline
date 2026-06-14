import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import EvalPage from "@/app/(dash)/eval/page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/hooks/useEvalQueue", () => ({
  useEvalQueue: () => ({ data: { documents: [], total: 0, offset: 0, limit: 50 }, isError: false }),
}));
vi.mock("@/hooks/useEval", () => ({
  useEvalPages: () => ({ data: { pages: [] }, isError: false }),
  useEnrol: () => ({ mutate: vi.fn(), isPending: false, data: undefined }),
  useSetLabel: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/components/EvalScorePanel", () => ({ EvalScorePanel: () => <div>score-panel</div> }));

describe("EvalPage", () => {
  it("defaults to the review queue tab", () => {
    render(<EvalPage />);
    expect(screen.getByText(/no documents need review/i)).toBeInTheDocument();
  });

  it("switches to the content-type lab tab", async () => {
    const user = userEvent.setup();
    render(<EvalPage />);
    await user.click(screen.getByRole("tab", { name: /content-type lab/i }));
    expect(screen.getByText("score-panel")).toBeInTheDocument();
  });
});
