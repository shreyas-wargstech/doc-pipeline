import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SearchResultsCard } from "@/components/aether/cards/SearchResultsCard";

describe("SearchResultsCard", () => {
  it("renders hits and a see-all link", () => {
    render(<SearchResultsCard result={{ kind: "search", total: 1,
      hits: [{ document_id: "7c20bd99", document_type: "application", page_type: "form" }] }} />);
    expect(screen.getByText(/7c20bd99/)).toBeInTheDocument();
    expect(screen.getByText(/Browse all documents/i)).toBeInTheDocument();
  });
  it("renders an empty state", () => {
    render(<SearchResultsCard result={{ kind: "search", total: 0, hits: [] }} />);
    expect(screen.getByText(/No documents found/i)).toBeInTheDocument();
  });
});
