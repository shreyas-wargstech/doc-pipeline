"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => apiGet<{ user: string }>("/api/me"), retry: false });
}

export function useLogin() {
  return useMutation({
    mutationFn: (creds: { username: string; password: string }) =>
      apiPost<{ user: string }>("/api/login", creds),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ ok: boolean }>("/api/logout"),
    onSuccess: () => { qc.clear(); window.location.assign("/login"); },
  });
}
