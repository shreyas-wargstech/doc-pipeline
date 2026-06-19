import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { ThemeProvider, useTheme } from "./theme";

let mediaListeners: Array<() => void>;
function stubMatchMedia(matches: boolean) {
  mediaListeners = [];
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches,
      media: "(prefers-color-scheme: dark)",
      addEventListener: (_: string, cb: () => void) => mediaListeners.push(cb),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    }))
  );
}

function TestConsumer() {
  const { theme, resolvedTheme, cycleTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button data-testid="cycle" onClick={cycleTheme}>cycle</button>
    </div>
  );
}

const renderWithProvider = () =>
  render(<ThemeProvider><TestConsumer /></ThemeProvider>);

describe("ThemeProvider", () => {
  beforeEach(() => {
    document.documentElement.classList.remove("dark");
    vi.stubGlobal("localStorage", { getItem: vi.fn(() => null), setItem: vi.fn() });
    stubMatchMedia(false); // OS = light by default
  });

  it("defaults to system and resolves to light when OS prefers light", () => {
    renderWithProvider();
    expect(screen.getByTestId("theme")).toHaveTextContent("system");
    expect(screen.getByTestId("resolved")).toHaveTextContent("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("system resolves to dark when OS prefers dark", () => {
    stubMatchMedia(true);
    renderWithProvider();
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("cycles system -> light -> dark -> system", () => {
    renderWithProvider();
    const btn = screen.getByTestId("cycle");
    expect(screen.getByTestId("theme")).toHaveTextContent("system");
    fireEvent.click(btn);
    expect(screen.getByTestId("theme")).toHaveTextContent("light");
    fireEvent.click(btn);
    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    fireEvent.click(btn);
    expect(screen.getByTestId("theme")).toHaveTextContent("system");
  });

  it("persists the chosen theme to localStorage", () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { getItem: vi.fn(() => null), setItem });
    renderWithProvider();
    fireEvent.click(screen.getByTestId("cycle")); // -> light
    expect(setItem).toHaveBeenCalledWith("docintel:theme", "light");
  });

  it("reads a persisted theme on mount", () => {
    vi.stubGlobal("localStorage", {
      getItem: vi.fn((k: string) => (k === "docintel:theme" ? "dark" : null)),
      setItem: vi.fn(),
    });
    renderWithProvider();
    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("live-updates when OS preference changes while in system mode", () => {
    renderWithProvider(); // system, OS light
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    // capture the listeners registered on the original stub before re-stubbing
    const listeners = [...mediaListeners];
    // simulate OS switching to dark
    stubMatchMedia(true);
    act(() => { listeners.forEach((cb) => cb()); });
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});
