import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { IdentityCard } from "@/components/aether/cards/IdentityCard";

describe("IdentityCard", () => {
  it("shows the score and summary", () => {
    render(<IdentityCard result={{ kind: "identity", consistency_score: 85, summary: "Name and reg agree." }} />);
    expect(screen.getByText("85")).toBeInTheDocument();
    expect(screen.getByText(/Name and reg agree/i)).toBeInTheDocument();
  });
});
