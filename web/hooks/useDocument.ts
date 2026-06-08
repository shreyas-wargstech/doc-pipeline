"use client";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { DocDetailResponse } from "@/lib/types";

export function useDocument(documentId: string) {
  return useQuery({
    queryKey: ["document", documentId],
    queryFn: () => apiGet<DocDetailResponse>(`/api/documents/${documentId}`),
  });
}
