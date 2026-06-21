import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WelcomeHero } from "@/components/aether/WelcomeHero";

describe("WelcomeHero", () => {
  it("renders capabilities and fires onPick", () => {
    const onPick = vi.fn();
    render(<WelcomeHero onPick={onPick} />);
    expect(screen.getByText(/what can i find/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Autopsy a document"));
    expect(onPick).toHaveBeenCalled();
  });
});
