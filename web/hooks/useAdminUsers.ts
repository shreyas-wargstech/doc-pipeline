"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";
import type { AdminUser, AdminUsersResponse, UserRole } from "@/lib/types";

const KEY = ["admin", "users"] as const;

export function useAdminUsers() {
  return useQuery({ queryKey: KEY, queryFn: () => apiGet<AdminUsersResponse>("/api/admin/users") });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { username: string; password: string; role: UserRole }) =>
      apiPost<AdminUser>("/api/admin/users", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateUserRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ username, role }: { username: string; role: UserRole }) =>
      apiPatch<AdminUser>(`/api/admin/users/${username}/role`, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useResetPassword() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      apiPatch<{ ok: boolean }>(`/api/admin/users/${username}/password`, { password }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useSetUserActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ username, is_active }: { username: string; is_active: boolean }) =>
      apiPatch<AdminUser>(`/api/admin/users/${username}/active`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (username: string) =>
      apiDelete<{ ok: boolean }>(`/api/admin/users/${username}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
