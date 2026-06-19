import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AccessibilityToolbar } from "./AccessibilityToolbar";
import { AccessibilityProvider } from "@/lib/accessibility";
import { ThemeProvider } from "@/lib/theme";

beforeEach(() => {
  document.documentElement.classList.remove("dark");
  vi.stubGlobal("localStorage", { getItem: vi.fn(() => null), setItem: vi.fn() });
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      media: "(prefers-color-scheme: dark)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    }))
  );
});

function renderWithProvider(ui: React.ReactNode) {
  return render(
    <ThemeProvider>
      <AccessibilityProvider>{ui}</AccessibilityProvider>
    </ThemeProvider>
  );
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

  it("renders the theme toggle starting in system mode", () => {
    renderWithProvider(<AccessibilityToolbar />);
    expect(screen.getByRole("button", { name: "Theme: system" })).toBeInTheDocument();
  });

  it("cycling the theme button advances system -> light", () => {
    renderWithProvider(<AccessibilityToolbar />);
    fireEvent.click(screen.getByRole("button", { name: "Theme: system" }));
    expect(screen.getByRole("button", { name: "Theme: light" })).toBeInTheDocument();
  });
});
