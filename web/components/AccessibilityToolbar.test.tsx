import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AccessibilityToolbar } from "./AccessibilityToolbar";
import { AccessibilityProvider } from "@/lib/accessibility";

function renderWithProvider(ui: React.ReactNode) {
  return render(<AccessibilityProvider>{ui}</AccessibilityProvider>);
}

describe("AccessibilityToolbar", () => {
  it("renders both toggle buttons", () => {
    renderWithProvider(<AccessibilityToolbar />);
    expect(screen.getByRole("button", { name: "High contrast mode" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Large text mode" })).toBeInTheDocument();
  });

  it("high-contrast button starts unpressed", () => {
    renderWithProvider(<AccessibilityToolbar />);
    const btn = screen.getByRole("button", { name: "High contrast mode" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
  });

  it("large-text button starts unpressed", () => {
    renderWithProvider(<AccessibilityToolbar />);
    const btn = screen.getByRole("button", { name: "Large text mode" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
  });

  it("clicking high-contrast toggles aria-pressed", () => {
    renderWithProvider(<AccessibilityToolbar />);
    const btn = screen.getByRole("button", { name: "High contrast mode" });
    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-pressed", "true");
  });

  it("clicking large-text toggles aria-pressed", () => {
    renderWithProvider(<AccessibilityToolbar />);
    const btn = screen.getByRole("button", { name: "Large text mode" });
    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-pressed", "true");
  });

  it("group has accessibility label", () => {
    renderWithProvider(<AccessibilityToolbar />);
    expect(screen.getByRole("group", { name: "Accessibility controls" })).toBeInTheDocument();
  });
});
