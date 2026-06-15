"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api";
import type { MeResponse, UserRole } from "@/lib/types";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => apiGet<MeResponse>("/api/me"),
    retry: false,
  });
}

export function useRole(): UserRole | null {
  const { data } = useMe();
  return data?.role ?? null;
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (creds: { username: string; password: string }) =>
      apiPost<MeResponse>("/api/login", creds),
    onSuccess: (data) => qc.setQueryData(["me"], data),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ ok: boolean }>("/api/logout"),
    onSuccess: () => { qc.clear(); window.location.assign("/login"); },
    onError: () => { qc.clear(); window.location.assign("/login"); },
  });
}
