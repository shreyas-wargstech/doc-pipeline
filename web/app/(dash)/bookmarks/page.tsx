"use client";
import { DocumentsTable } from "@/components/DocumentsTable";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useDocuments } from "@/hooks/useDocuments";

export default function BookmarksPage() {
  const q = useDocuments({ bookmarked: true });

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Bookmarks" subtitle="Documents you've bookmarked." />
      {q.isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
        </div>
      ) : q.isError ? (
        <p className="text-sm text-danger">Failed to load bookmarks.</p>
      ) : (
        <DocumentsTable rows={q.data!.documents} emptyText="No bookmarks yet." />
      )}
    </div>
  );
}
