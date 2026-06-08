"use client";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { MetricsResponse } from "@/lib/types";

export function useMetrics() {
  return useQuery({ queryKey: ["metrics"], queryFn: () => apiGet<MetricsResponse>("/api/metrics") });
}
