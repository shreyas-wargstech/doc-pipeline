import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { NarrativeCard } from "@/components/aether/cards/NarrativeCard";
import { AutopsyCard } from "@/components/aether/cards/AutopsyCard";

describe("simple cards", () => {
  it("narrative shows prose", () => {
    render(<NarrativeCard result={{ kind: "narrative", document_id: "abc123def", narrative: "A practitioner application." }} />);
    expect(screen.getByText(/practitioner application/i)).toBeInTheDocument();
  });
  it("autopsy lists stages + recommendation", () => {
    render(<AutopsyCard result={{ kind: "autopsy", overall_status: "manual_review",
      stages: [{ name: "match", status: "manual_review", detail: "name conflict" }],
      recommendation: "Open the form page." } as any} />);
    expect(screen.getByText(/name conflict/i)).toBeInTheDocument();
    expect(screen.getByText(/Open the form page/i)).toBeInTheDocument();
  });
});
