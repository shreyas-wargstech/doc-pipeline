import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CommandPalette } from "@/components/aether/CommandPalette";

describe("CommandPalette", () => {
  it("shows grouped templates when open and selects on click", () => {
    const onSelect = vi.fn();
    render(<CommandPalette open onOpenChange={() => {}} onSelect={onSelect} />);
    expect(screen.getByText("Diagnose")).toBeInTheDocument();
    fireEvent.click(screen.getByText("System health"));
    expect(onSelect).toHaveBeenCalledWith(expect.stringMatching(/system health/i));
  });
});
