"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api";
import type { EvalScore, EvalSweep } from "@/lib/types";
import type { EvalLabel, EvalPage } from "@/lib/eval-reducer";

export function useEvalPages(onlyUnlabeled = false) {
  return useQuery({
    queryKey: ["eval-pages", onlyUnlabeled],
    queryFn: () =>
      apiGet<{ pages: EvalPage[] }>(`/api/eval/pages?only_unlabeled=${onlyUnlabeled}`),
  });
}

export function useEvalScore() {
  return useQuery({ queryKey: ["eval-score"], queryFn: () => apiGet<EvalScore>("/api/eval/score") });
}

export function useEvalSweep() {
  return useQuery({ queryKey: ["eval-sweep"], queryFn: () => apiGet<EvalSweep>("/api/eval/sweep") });
}

export function useEnrol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string | null) =>
      apiPost<{ ok: boolean; enrolled?: number; message?: string }>(
        "/api/eval/enrol", { document_id: documentId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["eval-pages"] }),
  });
}

export function useSetLabel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ pageId, label }: { pageId: string; label: EvalLabel }) =>
      apiPost<{ ok: boolean; message?: string }>(
        `/api/eval/pages/${encodeURIComponent(pageId)}/label`, { label }),
    onSuccess: () => {
      // eval-pages too: a filtered (only_unlabeled) view must drop the row.
      qc.invalidateQueries({ queryKey: ["eval-pages"] });
      qc.invalidateQueries({ queryKey: ["eval-score"] });
      qc.invalidateQueries({ queryKey: ["eval-sweep"] });
    },
  });
}
