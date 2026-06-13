import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Breadcrumbs } from "@/components/Breadcrumbs";

const { usePathname } = vi.hoisted(() => ({ usePathname: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname }));

describe("Breadcrumbs", () => {
  it("shows just Documents at the root", () => {
    usePathname.mockReturnValue("/");
    render(<Breadcrumbs />);
    expect(screen.getByText("Documents")).toBeInTheDocument();
  });

  it("shows Documents > short id for a document detail page", () => {
    usePathname.mockReturnValue("/documents/abcdef1234567890");
    render(<Breadcrumbs />);
    expect(screen.getByRole("link", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByText("abcdef12…")).toBeInTheDocument();
  });

  it("shows Documents > short id > Page n for a page route", () => {
    usePathname.mockReturnValue("/documents/abcdef1234567890/pages/3");
    render(<Breadcrumbs />);
    expect(screen.getByRole("link", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "abcdef12…" })).toBeInTheDocument();
    expect(screen.getByText("Page 3")).toBeInTheDocument();
  });

  it("shows a labeled section name for top-level routes", () => {
    usePathname.mockReturnValue("/pipelines");
    render(<Breadcrumbs />);
    expect(screen.getByText("Pipelines")).toBeInTheDocument();
  });
});
