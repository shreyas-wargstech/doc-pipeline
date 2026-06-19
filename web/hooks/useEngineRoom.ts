"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  HealthReport,
  DiagnosticResult,
  TuningParameter,
  TuningSuggestion,
  ABTestResult,
  EngineCostSummary,
  InspectorReport,
  AutopsyReport,
} from "@/lib/types";

const API = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { credentials: "include" });
  if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`);
  return res.json();
}

export function useEngineHealth() {
  return useQuery<HealthReport>({
    queryKey: ["engine-health"],
    queryFn: () => get("/engine/health"),
    refetchInterval: 30000,
  });
}

export function useEngineDiagnostics() {
  return useQuery<{ results: DiagnosticResult[] }>({
    queryKey: ["engine-diagnostics"],
    queryFn: () => get("/engine/diagnostics"),
    enabled: false,
  });
}

export function useEngineParameters() {
  return useQuery<Record<string, TuningParameter>>({
    queryKey: ["engine-parameters"],
    queryFn: () => get("/engine/parameters"),
  });
}

export function useEngineTuningSuggestions() {
  return useQuery<{ suggestions: TuningSuggestion[] }>({
    queryKey: ["engine-tuning-suggestions"],
    queryFn: () => get("/engine/tuning/suggestions"),
  });
}

export function useUpdateParameter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      name,
      value,
      reason,
    }: {
      name: string;
      value: string;
      reason?: string;
    }) => post(`/engine/parameters/${name}`, { value, reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["engine-parameters"] });
      qc.invalidateQueries({ queryKey: ["engine-tuning-suggestions"] });
    },
  });
}

export function useTestParameter() {
  return useMutation({
    mutationFn: (body: {
      name: string;
      value: string;
      sample_size?: number;
    }) => post("/engine/parameters/test", body),
  });
}

export function useEngineABTest() {
  return useMutation({
    mutationFn: (body: {
      hypothesis: string;
      sample_size: number;
      variant: Record<string, unknown>;
    }) => post<ABTestResult>("/engine/ab-test", body),
  });
}

export function useEngineCostSummary() {
  return useQuery<EngineCostSummary>({
    queryKey: ["engine-cost-summary"],
    queryFn: () => get("/engine/costs/summary"),
  });
}

export function useEngineInspector(documentId: string | null) {
  return useQuery<InspectorReport>({
    queryKey: ["engine-inspector", documentId],
    queryFn: () => get(`/engine/inspector/${documentId}`),
    enabled: !!documentId,
  });
}

export function useAutopsy(documentId: string | null) {
  return useQuery<AutopsyReport>({
    queryKey: ["autopsy", documentId],
    queryFn: () => get(`/documents/${documentId}/autopsy`),
    enabled: !!documentId,
  });
}
