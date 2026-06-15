import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AdminUsersResponse, MeResponse } from "@/lib/types";

const mockUseAdminUsers = vi.fn();
const mockUseMe = vi.fn();
const mockUseRole = vi.fn();

vi.mock("@/hooks/useAdminUsers", () => ({
  useAdminUsers: () => mockUseAdminUsers(),
  useCreateUser: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateUserRole: () => ({ mutate: vi.fn() }),
  useResetPassword: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSetUserActive: () => ({ mutate: vi.fn() }),
  useDeleteUser: () => ({ mutate: vi.fn() }),
}));

vi.mock("@/hooks/useAuth", () => ({
  useMe: () => mockUseMe(),
  useRole: () => mockUseRole(),
  useLogin: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useLogout: () => ({ mutate: vi.fn() }),
}));

import AdminPage from "@/app/(dash)/admin/page";

const meAdmin: MeResponse = { user: "admin", role: "administrator" };
const usersData: AdminUsersResponse = {
  users: [
    { username: "admin", role: "administrator", is_active: true, created_at: "2026-01-01T00:00:00Z" },
    { username: "bob", role: "viewer", is_active: true, created_at: "2026-01-02T00:00:00Z" },
  ],
};

describe("AdminPage", () => {
  it("renders users table for admin", () => {
    mockUseRole.mockReturnValue("administrator");
    mockUseMe.mockReturnValue({ data: meAdmin });
    mockUseAdminUsers.mockReturnValue({ data: usersData, isLoading: false });
    render(<AdminPage />);
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
  });

  it("renders access denied for non-admin", () => {
    mockUseRole.mockReturnValue("viewer");
    mockUseMe.mockReturnValue({ data: { user: "bob", role: "viewer" } });
    mockUseAdminUsers.mockReturnValue({ data: null, isLoading: false });
    render(<AdminPage />);
    expect(screen.getByText(/access denied/i)).toBeInTheDocument();
  });

  it("shows invite user button", () => {
    mockUseRole.mockReturnValue("administrator");
    mockUseMe.mockReturnValue({ data: meAdmin });
    mockUseAdminUsers.mockReturnValue({ data: usersData, isLoading: false });
    render(<AdminPage />);
    expect(screen.getByRole("button", { name: /invite user/i })).toBeInTheDocument();
  });
});
