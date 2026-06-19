import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { HealthCard } from "@/components/aether/cards/HealthCard";

describe("HealthCard", () => {
  it("renders each check", () => {
    render(<HealthCard result={{ kind: "health", overall: "ok", checks: [
      { name: "postgres", status: "ok", detail: "reachable", latency_ms: 12 } as any] }} />);
    expect(screen.getByText(/postgres/i)).toBeInTheDocument();
    expect(screen.getByText(/12ms/)).toBeInTheDocument();
  });
});
