import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { InspectorCard } from "@/components/aether/cards/InspectorCard";

describe("InspectorCard", () => {
  it("renders all six pipeline stages", () => {
    render(<InspectorCard result={{ kind: "inspector", overall_status: "processed",
      stages: [{ stage: "ocr", status: "success", detail: "" }] }} />);
    ["Ingest", "OCR", "Structure", "Match", "Persist", "Index"].forEach((s) =>
      expect(screen.getByText(s)).toBeInTheDocument());
  });
});
