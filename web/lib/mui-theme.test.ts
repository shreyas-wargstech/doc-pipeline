import { describe, expect, it } from "vitest";
import { lightTheme, darkTheme } from "./mui-theme";

describe("mui-theme", () => {
  it("builds a light theme matching the CSS token palette", () => {
    expect(lightTheme.palette.mode).toBe("light");
    expect(lightTheme.palette.primary.main).toBe("rgb(30 64 175)");
    expect(lightTheme.palette.background.default).toBe("rgb(248 250 252)");
    expect(lightTheme.palette.background.paper).toBe("rgb(255 255 255)");
    expect(lightTheme.palette.error.main).toBe("rgb(220 38 38)");
    expect(lightTheme.palette.warning.main).toBe("rgb(146 64 10)");
    expect(lightTheme.palette.success.main).toBe("rgb(15 96 48)");
    expect(lightTheme.palette.info.main).toBe("rgb(67 56 202)");
  });

  it("builds a dark theme matching the CSS token palette", () => {
    expect(darkTheme.palette.mode).toBe("dark");
    expect(darkTheme.palette.primary.main).toBe("rgb(59 130 246)");
    expect(darkTheme.palette.background.default).toBe("rgb(11 18 32)");
    expect(darkTheme.palette.background.paper).toBe("rgb(19 28 46)");
  });
});
