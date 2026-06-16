import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "../Badge";

describe("Badge", () => {
  it("renders text content", () => {
    render(<Badge tone="ok">Matched</Badge>);
    expect(screen.getByText("Matched")).toBeInTheDocument();
  });

  it("renders an icon for ok tone", () => {
    render(<Badge tone="ok">Matched</Badge>);
    const icon = document.querySelector("[aria-hidden='true']");
    expect(icon).toBeInTheDocument();
  });

  it("renders an icon for warn tone", () => {
    render(<Badge tone="warn">Processing</Badge>);
    const icon = document.querySelector("[aria-hidden='true']");
    expect(icon).toBeInTheDocument();
  });

  it("renders an icon for danger tone", () => {
    render(<Badge tone="danger">Failed</Badge>);
    const icon = document.querySelector("[aria-hidden='true']");
    expect(icon).toBeInTheDocument();
  });

  it("renders an icon for info tone", () => {
    render(<Badge tone="info">Manual review</Badge>);
    const icon = document.querySelector("[aria-hidden='true']");
    expect(icon).toBeInTheDocument();
  });

  it("renders an icon for muted tone", () => {
    render(<Badge tone="muted">Received</Badge>);
    const icon = document.querySelector("[aria-hidden='true']");
    expect(icon).toBeInTheDocument();
  });

  it("icon has aria-hidden so screen readers skip it", () => {
    render(<Badge tone="ok">Matched</Badge>);
    const icon = document.querySelector("[aria-hidden='true']");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("badge text is visible for screen readers", () => {
    render(<Badge tone="ok">Matched</Badge>);
    expect(screen.getByText("Matched")).toBeVisible();
  });
});
