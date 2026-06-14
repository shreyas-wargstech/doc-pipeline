import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PageHeader } from "@/components/ui/PageHeader";

describe("PageHeader", () => {
  it("renders the title as a level-1 heading", () => {
    render(<PageHeader title="Documents" />);
    expect(screen.getByRole("heading", { level: 1, name: "Documents" })).toBeInTheDocument();
  });

  it("renders subtitle and actions when provided", () => {
    render(<PageHeader title="Documents" subtitle="3 bundles" actions={<button>Run</button>} />);
    expect(screen.getByText("3 bundles")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run" })).toBeInTheDocument();
  });
});
