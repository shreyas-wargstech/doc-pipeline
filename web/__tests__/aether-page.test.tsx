import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import AetherPage from "@/app/(dash)/aether/page";

vi.mock("@/hooks/useChat", () => ({
  useChat: () => ({
    messages: [{ role: "assistant", content: "I'm Aether, your pipeline assistant. Ask me about any document, system health, or pipeline status.", timestamp: "" }],
    send: vi.fn(), isLoading: false, recent: [], clearThread: vi.fn(),
  }),
}));

describe("AetherPage", () => {
  it("shows the welcome hero on an empty thread", () => {
    render(<AetherPage />);
    expect(screen.getByText(/what can i find for you/i)).toBeInTheDocument();
  });
});
