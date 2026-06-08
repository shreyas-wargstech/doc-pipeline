import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";

describe("StatusBadge", () => {
  it("shows readable label + a non-color text cue for failed", () => {
    render(<StatusBadge status="failed" />);
    const el = screen.getByText(/failed/i);
    expect(el).toBeInTheDocument();
  });
  it("renders processing label", () => {
    render(<StatusBadge status="processing" />);
    expect(screen.getByText(/processing/i)).toBeInTheDocument();
  });
});

describe("MatchBadge", () => {
  it("renders an em dash for null match_status", () => {
    render(<MatchBadge status={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
  it("renders matched", () => {
    render(<MatchBadge status="matched" />);
    expect(screen.getByText(/matched/i)).toBeInTheDocument();
  });
});
