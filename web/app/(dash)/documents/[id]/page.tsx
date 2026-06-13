"use client";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import { ActionButtons } from "@/components/ActionButtons";
import { PageGrid } from "@/components/PageGrid";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { useDocument } from "@/hooks/useDocument";
import { fmtDateTime, titleCase } from "@/lib/format";

export default function DocumentDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const q = useDocument(id);

  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError || !q.data) return <p className="text-sm text-danger">Failed to load document.</p>;
  const { doc, pages, ocr_done, structured_done } = q.data;

  return (
    <div className="flex flex-col gap-4">
      <Link href="/" className="inline-flex w-fit items-center gap-1 text-sm text-muted-fg hover:text-foreground"><ArrowLeft className="h-4 w-4" />Documents</Link>

      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-lg font-semibold text-foreground">{doc.registration_no ?? doc.original_filename}</h1>
          <StatusBadge status={doc.status} />
          <MatchBadge status={doc.match_status} />
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
          <Field k="Category" v={titleCase(doc.document_category)} />
          <Field k="Type" v={titleCase(doc.document_type)} />
          <Field k="Applicant" v={doc.applicant_name_raw ?? "—"} />
          <Field k="Doc ref." v={doc.document_reference_no ?? "—"} mono />
          <Field k="Application no." v={doc.application_no?.toString() ?? "—"} mono />
          <Field k="DOB" v={doc.dob ?? "—"} />
          <Field k="OCR" v={`${ocr_done}/${doc.page_count}`} />
          <Field k="Structured" v={`${structured_done}/${doc.page_count}`} />
          <Field k="Updated" v={fmtDateTime(doc.updated_at)} />
        </dl>
        {doc.document_summary && (
          <p className="text-sm text-muted-fg">{doc.document_summary}</p>
        )}
        <ActionButtons documentId={doc.document_id} />
      </Card>

      <PageGrid documentId={doc.document_id} pages={pages} />
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
