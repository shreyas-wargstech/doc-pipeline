import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ComingSoon } from "@/components/ComingSoon";

describe("ComingSoon", () => {
  it("renders the title and each planned item", () => {
    render(<ComingSoon title="Pipelines" items={["Pipeline status overview", "Last run history"]} />);
    expect(screen.getByRole("heading", { name: "Pipelines" })).toBeInTheDocument();
    expect(screen.getByText("Pipeline status overview")).toBeInTheDocument();
    expect(screen.getByText("Last run history")).toBeInTheDocument();
  });
});
