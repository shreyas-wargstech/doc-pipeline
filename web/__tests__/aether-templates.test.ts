import { describe, it, expect } from "vitest";
import { TEMPLATES } from "@/components/aether/templates";

describe("templates", () => {
  it("has grouped templates with required fields", () => {
    expect(TEMPLATES.length).toBeGreaterThanOrEqual(5);
    for (const t of TEMPLATES) {
      expect(t.group).toMatch(/Diagnose|Find|System/);
      expect(typeof t.needsDoc).toBe("boolean");
      expect(typeof t.llm).toBe("boolean");
    }
  });
  it("marks system health as free (non-llm)", () => {
    const health = TEMPLATES.find((t) => t.id === "health");
    expect(health?.llm).toBe(false);
  });
});
