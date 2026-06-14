"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { EvalCorrectionForm } from "@/components/EvalCorrectionForm";
import { Skeleton } from "@/components/ui/Skeleton";
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
  if (q.isError || !q.data) return <Typography color="error" variant="body2">Failed to load document.</Typography>;

  const { doc, pages } = q.data;
  const focusPage = pages.find((p) => p.page_type === "application_form") ?? pages[0];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Link href="/eval" className="inline-flex w-fit items-center gap-1 text-sm text-muted-fg hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />Review queue
      </Link>
      <Typography variant="h6" component="h1" sx={{ fontFamily: "var(--font-mono)" }}>
        {doc.document_reference_no ?? doc.original_filename}
      </Typography>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "1fr 1fr" } }}>
        <Paper sx={{ overflow: "hidden" }}>
          {focusPage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageUrl(id, focusPage.page_num)}
              alt={`Page ${focusPage.page_num}`}
              style={{ width: "100%", display: "block" }}
            />
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>No pages.</Typography>
          )}
        </Paper>
        <EvalCorrectionForm doc={doc} />
      </Box>
    </Box>
  );
}
