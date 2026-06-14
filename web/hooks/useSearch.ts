"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { SearchPagesResponse, SearchResponse } from "@/lib/types";

export function useSearch(query: string) {
  return useQuery({
    queryKey: ["search", query],
    queryFn: () => apiGet<SearchResponse>(`/api/search?q=${encodeURIComponent(query)}`),
    enabled: query.trim().length > 0,
    placeholderData: keepPreviousData,
  });
}

export function useSearchDocPages(documentId: string | null) {
  return useQuery({
    queryKey: ["search-pages", documentId],
    queryFn: () => apiGet<SearchPagesResponse>(`/api/search/${documentId}/pages`),
    enabled: documentId !== null,
  });
}
