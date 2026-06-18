"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { EvalCorrectionForm } from "@/components/EvalCorrectionForm";
import { useDocument } from "@/hooks/useDocument";
import { imageUrl } from "@/lib/api";

export default function EvalDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [resolved, setResolved] = useState<{ id: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    params.then((p) => {
      if (!cancelled) setResolved(p);
    });
    return () => {
      cancelled = true;
    };
  }, [params]);

  const id = resolved?.id ?? "";
  const q = useDocument(id);

  if (!resolved || q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError || !q.data) return <p className="text-sm text-danger">Failed to load document.</p>;

  const { doc, pages } = q.data;
  const focusPage = pages.find((p) => p.page_type === "application_form") ?? pages[0];

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <Link href="/eval" className="inline-flex w-fit items-center gap-1 text-sm text-muted-fg hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />Review queue
      </Link>
      <h1 className="font-mono text-xl font-semibold text-foreground">
        {doc.document_reference_no ?? doc.original_filename}
      </h1>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden p-0">
          {focusPage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageUrl(id, focusPage.page_num)}
              alt={`Page ${focusPage.page_num}`}
              className="w-full block"
            />
          ) : (
            <p className="p-4 text-sm text-muted-fg">No pages.</p>
          )}
        </Card>
        <EvalCorrectionForm doc={doc} />
      </div>
    </div>
  );
}
