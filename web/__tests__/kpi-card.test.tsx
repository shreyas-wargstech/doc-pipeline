import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KpiCard } from "@/components/KpiCard";

describe("KpiCard", () => {
  it("renders label and value", () => {
    render(<KpiCard label="Matched" value={42} tone="ok" />);
    expect(screen.getByText("Matched")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders a card root", () => {
    render(<KpiCard label="Total" value={10} />);
    expect(document.querySelector("[class*='rounded-lg']")).toBeInTheDocument();
  });
});
