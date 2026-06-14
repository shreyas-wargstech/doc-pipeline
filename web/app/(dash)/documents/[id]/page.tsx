"use client";
import { useEffect, useMemo, useState } from "react";
import { ActionButtons } from "@/components/ActionButtons";
import { BookmarkStar } from "@/components/BookmarkStar";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { useDocument } from "@/hooks/useDocument";
import { useSetActionBar } from "@/app/action-bar";
import { fmtDateTime, titleCase } from "@/lib/format";

export default function DocumentDetail({ params }: { params: Promise<{ id: string }> }) {
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

  const actionBarContent = useMemo(
    () => (q.data?.doc ? <ActionButtons documentId={q.data.doc.document_id} /> : null),
    [q.data?.doc?.document_id],
  );
  useSetActionBar(actionBarContent);

  if (!resolved || q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError || !q.data || !q.data.doc) return <p className="text-sm text-danger">Failed to load document.</p>;
  const { doc, ocr_done, structured_done } = q.data;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={doc.registration_no ?? doc.original_filename}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={doc.status} />
            <MatchBadge status={doc.match_status} />
          </span>
        }
        actions={<BookmarkStar documentId={doc.document_id} bookmarked={doc.bookmarked} />}
      />

      <Card className="flex flex-col gap-3">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
          <Field k="Category" v={titleCase(doc.document_category)} />
          <Field k="Type" v={titleCase(doc.document_type)} />
          <Field k="Applicant" v={doc.applicant_name_raw ?? "—"} />
          <Field k="Doc ref." v={doc.document_reference_no ?? "—"} mono />
          <Field k="Application no." v={doc.application_no?.toString() ?? "—"} mono />
          <Field k="Registration no." v={doc.registration_no ?? "—"} mono />
          <Field k="DOB" v={doc.dob ?? "—"} />
          <Field k="OCR" v={`${ocr_done}/${doc.page_count}`} />
          <Field k="Structured" v={`${structured_done}/${doc.page_count}`} />
          <Field k="Updated" v={fmtDateTime(doc.updated_at)} />
        </dl>
      </Card>

      {doc.document_summary && (
        <p className="font-sans text-sm leading-relaxed text-muted-fg">{doc.document_summary}</p>
      )}
    </div>
  );
}

function Field({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs uppercase tracking-wide text-muted-fg">{k}</dt>
      <dd className={`text-foreground ${mono ? "font-mono" : ""}`}>{v}</dd>
    </div>
  );
}
