import { render, screen, act } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { ThemeModeProvider, useThemeMode } from "@/app/theme-mode";

function Probe() {
  const { mode, toggle } = useThemeMode();
  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <button onClick={toggle}>toggle</button>
    </div>
  );
}

describe("ThemeModeProvider", () => {
  beforeEach(() => {
    document.documentElement.classList.remove("dark");
    localStorage.clear();
  });

  it("defaults to light and toggles to dark, updating the html class", async () => {
    render(<ThemeModeProvider><Probe /></ThemeModeProvider>);
    expect(screen.getByTestId("mode").textContent).toBe("light");

    await act(async () => {
      screen.getByRole("button", { name: "toggle" }).click();
    });

    expect(screen.getByTestId("mode").textContent).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("picks up an existing dark class on mount", () => {
    document.documentElement.classList.add("dark");
    render(<ThemeModeProvider><Probe /></ThemeModeProvider>);
    expect(screen.getByTestId("mode").textContent).toBe("dark");
  });
});
