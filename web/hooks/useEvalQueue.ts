"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch } from "@/lib/api";
import type { CorrectionPatch, CorrectionResult, EvalQueueResponse } from "@/lib/types";

export function useEvalQueue(offset = 0) {
  return useQuery({
    queryKey: ["eval-queue", offset],
    queryFn: () => apiGet<EvalQueueResponse>(`/api/eval/queue?offset=${offset}`),
  });
}

export function useCorrectDocument(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: CorrectionPatch) =>
      apiPatch<CorrectionResult>(`/api/eval/queue/${documentId}`, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["eval-queue"] });
      qc.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });
}
