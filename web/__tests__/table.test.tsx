import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Table } from "@/components/ui/Table";

describe("Table", () => {
  it("renders headers and rows", () => {
    render(
      <Table
        columns={[{ key: "a", header: "Col A" }, { key: "b", header: "Col B" }]}
        rows={[{ a: "x1", b: "y1" }, { a: "x2", b: "y2" }]}
        rowKey={(r) => String(r.a)}
      />,
    );
    expect(screen.getByText("Col A")).toBeInTheDocument();
    expect(screen.getByText("x2")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("shows empty state when no rows", () => {
    render(<Table columns={[{ key: "a", header: "A" }]} rows={[]} rowKey={() => "k"} empty="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
});
