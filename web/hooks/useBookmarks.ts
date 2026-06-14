"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiPost } from "@/lib/api";

/**
 * Toggle a document's bookmark. `mutate(next)` where next=true bookmarks
 * (POST) and next=false un-bookmarks (DELETE). On success, invalidates the
 * documents list (includes the Bookmarks page) and this document's detail so
 * every surface re-reads the authoritative flag.
 */
export function useToggleBookmark(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (next: boolean) =>
      next
        ? apiPost<{ bookmarked: boolean }>(`/api/documents/${documentId}/bookmark`)
        : apiDelete<{ bookmarked: boolean }>(`/api/documents/${documentId}/bookmark`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });
}
