import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AccessibilityProvider, useAccessibility } from "./accessibility";

function TestConsumer() {
  const { highContrast, largeText, toggleHighContrast, toggleLargeText } = useAccessibility();
  return (
    <div>
      <span data-testid="hc">{highContrast ? "on" : "off"}</span>
      <span data-testid="lt">{largeText ? "on" : "off"}</span>
      <button data-testid="toggle-hc" onClick={toggleHighContrast}>Toggle HC</button>
      <button data-testid="toggle-lt" onClick={toggleLargeText}>Toggle LT</button>
    </div>
  );
}

function renderWithProvider(ui: React.ReactNode) {
  return render(<AccessibilityProvider>{ui}</AccessibilityProvider>);
}

describe("AccessibilityProvider", () => {
  beforeEach(() => {
    document.documentElement.classList.remove("high-contrast", "large-text");
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
    });
  });

  it("defaults both toggles to off", () => {
    renderWithProvider(<TestConsumer />);
    expect(screen.getByTestId("hc")).toHaveTextContent("off");
    expect(screen.getByTestId("lt")).toHaveTextContent("off");
  });

  it("toggles high-contrast on click", () => {
    renderWithProvider(<TestConsumer />);
    fireEvent.click(screen.getByTestId("toggle-hc"));
    expect(screen.getByTestId("hc")).toHaveTextContent("on");
    expect(document.documentElement.classList.contains("high-contrast")).toBe(true);
  });

  it("toggles high-contrast off on second click", () => {
    renderWithProvider(<TestConsumer />);
    fireEvent.click(screen.getByTestId("toggle-hc"));
    fireEvent.click(screen.getByTestId("toggle-hc"));
    expect(screen.getByTestId("hc")).toHaveTextContent("off");
    expect(document.documentElement.classList.contains("high-contrast")).toBe(false);
  });

  it("toggles large-text on click", () => {
    renderWithProvider(<TestConsumer />);
    fireEvent.click(screen.getByTestId("toggle-lt"));
    expect(screen.getByTestId("lt")).toHaveTextContent("on");
    expect(document.documentElement.classList.contains("large-text")).toBe(true);
  });

  it("reads persisted high-contrast from localStorage", () => {
    vi.stubGlobal("localStorage", {
      getItem: vi.fn((key: string) => (key === "docintel:high-contrast" ? "true" : null)),
      setItem: vi.fn(),
    });
    renderWithProvider(<TestConsumer />);
    expect(screen.getByTestId("hc")).toHaveTextContent("on");
  });

  it("reads persisted large-text from localStorage", () => {
    vi.stubGlobal("localStorage", {
      getItem: vi.fn((key: string) => (key === "docintel:large-text" ? "true" : null)),
      setItem: vi.fn(),
    });
    renderWithProvider(<TestConsumer />);
    expect(screen.getByTestId("lt")).toHaveTextContent("on");
  });

  it("persists high-contrast to localStorage", () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { getItem: vi.fn(() => null), setItem });
    renderWithProvider(<TestConsumer />);
    fireEvent.click(screen.getByTestId("toggle-hc"));
    expect(setItem).toHaveBeenCalledWith("docintel:high-contrast", "true");
  });

  it("persists large-text to localStorage", () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { getItem: vi.fn(() => null), setItem });
    renderWithProvider(<TestConsumer />);
    fireEvent.click(screen.getByTestId("toggle-lt"));
    expect(setItem).toHaveBeenCalledWith("docintel:large-text", "true");
  });
});
