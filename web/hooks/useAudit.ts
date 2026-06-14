"use client";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { AuditResponse } from "@/lib/types";

export interface AuditFilters { username?: string; document_id?: string; action?: string; result?: string; }

export function useAudit(f: AuditFilters) {
  const p = new URLSearchParams();
  if (f.username) p.set("username", f.username);
  if (f.document_id) p.set("document_id", f.document_id);
  if (f.action) p.set("action", f.action);
  if (f.result) p.set("result", f.result);
  const qs = p.toString();
  return useQuery({
    queryKey: ["audit", f],
    queryFn: () => apiGet<AuditResponse>(`/api/audit${qs ? `?${qs}` : ""}`),
  });
}
