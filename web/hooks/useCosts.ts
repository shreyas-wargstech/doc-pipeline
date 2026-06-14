"use client";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { CostsResponse, CostEventsResponse } from "@/lib/types";

export function useCosts() {
  return useQuery({ queryKey: ["costs"], queryFn: () => apiGet<CostsResponse>("/api/costs") });
}

export function useCostEvents(stage?: string, limit = 50) {
  const p = new URLSearchParams();
  if (stage) p.set("stage", stage);
  if (limit) p.set("limit", String(limit));
  const qs = p.toString();
  return useQuery({
    queryKey: ["cost-events", stage, limit],
    queryFn: () => apiGet<CostEventsResponse>(`/api/costs/events${qs ? `?${qs}` : ""}`),
  });
}
