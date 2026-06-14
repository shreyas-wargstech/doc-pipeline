import { describe, expect, it } from "vitest";
import { theme } from "./mui-theme";

describe("mui-theme", () => {
  it("is a single warm light theme", () => {
    expect(theme.palette.mode).toBe("light");
    expect(theme.palette.primary.main).toBe("rgb(13 148 136)");
    expect(theme.palette.background.default).toBe("rgb(251 250 247)");
    expect(theme.palette.background.paper).toBe("rgb(255 255 255)");
    expect(theme.palette.warning.main).toBe("rgb(154 106 26)");
    expect(theme.palette.error.main).toBe("rgb(180 35 24)");
  });

  it("uses editorial typography and soft radius", () => {
    expect(theme.shape.borderRadius).toBe(10);
    expect(theme.typography.button.textTransform).toBe("none");
    expect(String(theme.typography.h1.fontFamily)).toContain("--font-display");
    expect(String(theme.typography.body1.fontFamily)).toContain("--font-sans");
  });

  it("applies warm shadows and component overrides", () => {
    expect(theme.shadows[1]).toContain("rgba(70,55,30");
    expect(theme.components?.MuiButton?.styleOverrides).toBeDefined();
    expect(theme.components?.MuiAppBar?.defaultProps?.elevation).toBe(0);
  });
});
