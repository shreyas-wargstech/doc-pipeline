import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/AppShell";

const { usePathname } = vi.hoisted(() => ({ usePathname: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname }));

vi.mock("@/hooks/useAuth", () => ({ useLogout: () => ({ mutate: vi.fn() }) }));

vi.mock("@/app/action-bar", () => ({
  useActionBarContent: () => null,
}));

describe("AppShell", () => {
  it("renders all six top-level nav groups", () => {
    usePathname.mockReturnValue("/");
    render(<AppShell><div>content</div></AppShell>);
    for (const label of ["Documents", "Evaluation", "Pipelines", "Retrieval", "Observability", "Admin"]) {
      expect(screen.getByRole("link", { name: new RegExp(label, "i") })).toBeInTheDocument();
    }
  });

  it("marks the active route with aria-current", () => {
    usePathname.mockReturnValue("/pipelines");
    render(<AppShell><div>content</div></AppShell>);
    expect(screen.getByRole("link", { name: /pipelines/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /documents/i })).not.toHaveAttribute("aria-current");
  });

  it("renders breadcrumbs and children", () => {
    usePathname.mockReturnValue("/");
    render(<AppShell><div>page content</div></AppShell>);
    expect(screen.getByText("page content")).toBeInTheDocument();
    expect(screen.getByText("Docintel")).toBeInTheDocument();
  });

  it("toggles the desktop sidebar collapsed state", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    usePathname.mockReturnValue("/");
    window.localStorage.clear();
    render(<AppShell><div>content</div></AppShell>);
    const toggle = screen.getByRole("button", { name: /collapse sidebar/i });
    await userEvent.click(toggle);
    expect(window.localStorage.getItem("collapse:app-sidebar")).toBe("true");
  });
});
