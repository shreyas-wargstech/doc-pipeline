import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

if (!window.matchMedia) {
  // @ts-expect-error jsdom lacks matchMedia
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
}

const mutateAsync = vi.fn().mockResolvedValue({ user: "u" });
vi.mock("@/hooks/useAuth", () => ({
  useLogin: () => ({ mutateAsync, isPending: false }),
}));
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

import LoginPage from "@/app/login/page";

describe("LoginPage", () => {
  it("renders the brand panel headline and the sign-in form", () => {
    render(<LoginPage />);
    expect(screen.getByText("Welcome back")).toBeInTheDocument();
    expect(screen.getByText(/Every document/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("toggles password visibility", () => {
    render(<LoginPage />);
    const pw = screen.getByLabelText(/password/i) as HTMLInputElement;
    expect(pw.type).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: /show password/i }));
    expect(pw.type).toBe("text");
  });

  it("submits credentials and redirects", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: /^sign in$/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ username: "alice", password: "pw" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });
});
