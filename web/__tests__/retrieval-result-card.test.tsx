import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResultCard } from "@/components/retrieval/ResultCard";
import type { RetrievalHit } from "@/lib/types";

function hit(over: Partial<RetrievalHit> = {}): RetrievalHit {
  return {
    document_id: "a3f8c2b1e9084f5d7c6a0d3e2f1b4c8ad291",
    s3_key_pdf: "x.pdf",
    document_type: "practitioner_application",
    score: 1,
    tier: 1,
    why_matched: "keyword match: kulkarni, priya",
    ...over,
  };
}

describe("ResultCard", () => {
  it("renders the tier label for each tier", () => {
    const { rerender } = render(<ResultCard hit={hit({ tier: 1 })} selected={false} onClick={() => {}} />);
    expect(screen.getByText("Keyword")).toBeInTheDocument();
    rerender(<ResultCard hit={hit({ tier: 2 })} selected={false} onClick={() => {}} />);
    expect(screen.getByText("Graph")).toBeInTheDocument();
    rerender(<ResultCard hit={hit({ tier: 3 })} selected={false} onClick={() => {}} />);
    expect(screen.getByText("Vector")).toBeInTheDocument();
  });

  it("shows the why_matched text and a truncated document id", () => {
    render(<ResultCard hit={hit()} selected={false} onClick={() => {}} />);
    expect(screen.getByText(/keyword match: kulkarni/i)).toBeInTheDocument();
    // truncated: first 8 + ellipsis + last 4
    expect(screen.getByText(/a3f8c2b1…d291/)).toBeInTheDocument();
  });

  it("fires onClick when clicked", async () => {
    const onClick = vi.fn();
    render(<ResultCard hit={hit()} selected={false} onClick={onClick} />);
    screen.getByRole("button").click();
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("marks itself selected via aria-pressed", () => {
    render(<ResultCard hit={hit()} selected onClick={() => {}} />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });
});
