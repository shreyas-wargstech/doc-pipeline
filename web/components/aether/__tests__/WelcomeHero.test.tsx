import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WelcomeHero } from "@/components/aether/WelcomeHero";

describe("WelcomeHero", () => {
  it("renders capabilities and fires onPick", () => {
    const onPick = vi.fn();
    render(<WelcomeHero recent={["Pages for Dr. Sharma"]} onPick={onPick} />);
    expect(screen.getByText(/what can i find/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Pages for Dr. Sharma"));
    expect(onPick).toHaveBeenCalledWith("Pages for Dr. Sharma");
  });
});
