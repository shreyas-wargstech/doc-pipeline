import { describe, it, expect } from "vitest";
import { colorTriplets, darkColorTriplets, themeCssVars } from "./tokens";

describe("tokens", () => {
  it("dark triplets cover exactly the same keys as light", () => {
    expect(Object.keys(darkColorTriplets).sort()).toEqual(
      Object.keys(colorTriplets).sort()
    );
  });

  it("every triplet is three space-separated 0-255 integers", () => {
    for (const v of [...Object.values(colorTriplets), ...Object.values(darkColorTriplets)]) {
      const parts = v.split(" ");
      expect(parts).toHaveLength(3);
      for (const p of parts) {
        const n = Number(p);
        expect(Number.isInteger(n)).toBe(true);
        expect(n).toBeGreaterThanOrEqual(0);
        expect(n).toBeLessThanOrEqual(255);
      }
    }
  });

  it("includes a shadow token in both palettes", () => {
    expect(colorTriplets.shadow).toBe("60 45 25");
    expect(darkColorTriplets.shadow).toBe("0 0 0");
  });

  it("themeCssVars emits :root light defaults and a .dark override block", () => {
    expect(themeCssVars).toContain(":root{");
    expect(themeCssVars).toContain(".dark{");
    // light background present in :root, dark background present in .dark
    expect(themeCssVars).toContain("--color-background: 249 247 244");
    expect(themeCssVars).toContain("--color-background: 12 20 19");
  });

  it("declares color-scheme for native UI", () => {
    expect(themeCssVars).toContain("color-scheme:light");
    expect(themeCssVars).toContain(".dark{color-scheme:dark}");
  });

  it("dark override uses a bare .dark selector so html.high-contrast outranks it", () => {
    // .dark (0,1,0) must lose to html.high-contrast (0,1,1)
    expect(themeCssVars).not.toContain("html.dark{");
    expect(themeCssVars).toMatch(/(^|})\.dark\{/);
  });
});
