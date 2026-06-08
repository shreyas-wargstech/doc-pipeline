"use client";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { PageDetailResponse } from "@/lib/types";

export function usePage(documentId: string, pageNum: number) {
  return useQuery({
    queryKey: ["page", documentId, pageNum],
    queryFn: () => apiGet<PageDetailResponse>(`/api/documents/${documentId}/pages/${pageNum}`),
  });
}
