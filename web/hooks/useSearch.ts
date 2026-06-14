"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { SearchPagesResponse, SearchResponse } from "@/lib/types";

export function useSearch(query: string) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["search", query],
    queryFn: () => apiGet<SearchResponse>(`/api/search?q=${encodeURIComponent(query)}`),
    enabled: query.trim().length > 0,
    placeholderData: keepPreviousData,
  });
  return { data, isLoading, isError };
}

export function useSearchDocPages(documentId: string | null) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["search-pages", documentId],
    queryFn: () => apiGet<SearchPagesResponse>(`/api/search/${documentId}/pages`),
    enabled: documentId !== null,
  });
  return { data, isLoading, isError };
}
