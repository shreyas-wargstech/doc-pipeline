import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProgressBar } from "@/components/ui/ProgressBar";

describe("ProgressBar", () => {
  it("exposes aria valuenow/min/max and clamps over-100", () => {
    render(<ProgressBar done={5} total={3} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuemax", "3");
    expect(bar).toHaveAttribute("aria-valuenow", "3");
  });
  it("shows done/total label", () => {
    render(<ProgressBar done={2} total={4} />);
    expect(screen.getByText("2/4")).toBeInTheDocument();
  });
  it("handles zero total without NaN", () => {
    render(<ProgressBar done={0} total={0} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });
});
