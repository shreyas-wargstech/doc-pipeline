"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { Category, DocStatus, DocumentsResponse, MatchStatus } from "@/lib/types";

export interface DocFilters {
  category?: Category;
  status?: DocStatus;
  match_status?: NonNullable<MatchStatus>;
  search?: string;
  bookmarked?: boolean;
  offset?: number;
}

export function buildQuery(f: DocFilters): string {
  const p = new URLSearchParams();
  if (f.category) p.set("category", f.category);
  if (f.status) p.set("status", f.status);
  if (f.match_status) p.set("match_status", f.match_status);
  if (f.search) p.set("search", f.search);
  if (f.bookmarked) p.set("bookmarked", "true");
  if (f.offset) p.set("offset", String(f.offset));
  const qs = p.toString();
  return `/api/documents${qs ? `?${qs}` : ""}`;
}

export function useDocuments(f: DocFilters) {
  return useQuery({
    queryKey: ["documents", f],
    queryFn: () => apiGet<DocumentsResponse>(buildQuery(f)),
    placeholderData: keepPreviousData,
  });
}
