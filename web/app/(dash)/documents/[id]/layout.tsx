"use client";
import { use } from "react";
import { Skeleton } from "@/components/ui/Skeleton";
import { RailContext } from "@/components/PageRailContext";
import { PageRail } from "@/components/PageRail";
import { useDocument } from "@/hooks/useDocument";
import { useCollapsible } from "@/hooks/useCollapsible";

export default function DocumentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const q = useDocument(id);
  const rail = useCollapsible("page-rail", false);

  return (
    <RailContext.Provider value={rail}>
      <div className="flex gap-4">
        {q.isLoading ? (
          <div
            className="hidden flex-shrink-0 flex-col gap-2 sm:flex"
            style={{ width: rail.collapsed ? 56 : 200 }}
          >
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : q.data ? (
          <PageRail documentId={id} pages={q.data.pages} collapsed={rail.collapsed} />
        ) : null}
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </RailContext.Provider>
  );
}
