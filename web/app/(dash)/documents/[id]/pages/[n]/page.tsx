"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import ArrowBackIosNewIcon from "@mui/icons-material/ArrowBackIosNew";
import ArrowForwardIosIcon from "@mui/icons-material/ArrowForwardIos";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { JsonViewer } from "@/components/JsonViewer";
import { Skeleton } from "@/components/ui/Skeleton";
import { imageUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { useDocument } from "@/hooks/useDocument";
import { usePage } from "@/hooks/usePage";
import { useToast } from "@/app/providers";

export default function PageDetail({ params }: { params: Promise<{ id: string; n: string }> }) {
  const [resolved, setResolved] = useState<{ id: string; n: string } | null>(null);
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
  const n = resolved?.n ?? "0";
  const pageNum = Number(n);
  const router = useRouter();
  const { push: pushToast } = useToast();
  const q = usePage(id, pageNum);
  const docQuery = useDocument(id);
  const [tab, setTab] = useState<number | null>(null);

  const pageCount = docQuery.data?.doc.page_count ?? null;
  const hasPrev = pageNum > 1;
  const hasNext = pageCount != null && pageNum < pageCount;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft" && hasPrev) router.push(`/documents/${id}/pages/${pageNum - 1}`);
      if (e.key === "ArrowRight" && hasNext) router.push(`/documents/${id}/pages/${pageNum + 1}`);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [id, pageNum, hasPrev, hasNext, router]);

  if (!resolved || q.isLoading) return <Skeleton className="h-96 w-full" />;
  if (q.isError || !q.data) return <Typography color="error" variant="body2">Failed to load page.</Typography>;
  const { page, structured_json, raw_text } = q.data;

  const defaultTab = page.page_summary ? 0 : 1;
  const activeTab = tab ?? defaultTab;

  const copyLink = async () => {
    await navigator.clipboard.writeText(window.location.href);
    pushToast("ok", "Link copied to clipboard");
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <IconButton
          component={Link}
          href={hasPrev ? `/documents/${id}/pages/${pageNum - 1}` : `/documents/${id}/pages/${pageNum}`}
          aria-label="Previous page"
          aria-disabled={!hasPrev}
          onClick={(e) => {
            if (!hasPrev) e.preventDefault();
          }}
          tabIndex={hasPrev ? undefined : -1}
          size="small"
        >
          <ArrowBackIosNewIcon fontSize="small" />
        </IconButton>
        <Typography variant="h6" component="h1" sx={{ fontFamily: "var(--font-mono)" }}>
          Page {page.page_num}
        </Typography>
        <IconButton
          component={Link}
          href={hasNext ? `/documents/${id}/pages/${pageNum + 1}` : `/documents/${id}/pages/${pageNum}`}
          aria-label="Next page"
          aria-disabled={!hasNext}
          onClick={(e) => {
            if (!hasNext) e.preventDefault();
          }}
          tabIndex={hasNext ? undefined : -1}
          size="small"
        >
          <ArrowForwardIosIcon fontSize="small" />
        </IconButton>

        <Chip size="small" label={titleCase(page.page_type)} />
        <Chip size="small" color={page.ocr_status === "done" ? "success" : "warning"} label={page.ocr_status} />
        {page.language_detected && <Chip size="small" color="info" label={page.language_detected} />}
        {page.confidence_score != null && (
          <Typography variant="caption" className="tnum" color="text.secondary">
            conf {page.confidence_score.toFixed(0)}
          </Typography>
        )}

        <IconButton aria-label="Copy link" size="small" onClick={copyLink} sx={{ ml: "auto" }}>
          <ContentCopyIcon fontSize="small" />
        </IconButton>
      </Box>

      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "1fr 1fr" } }}>
        <Paper sx={{ overflow: "hidden" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imageUrl(id, pageNum)} alt={`Page ${pageNum}`} style={{ width: "100%", display: "block" }} />
        </Paper>

        {hasPrev && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl(id, pageNum - 1)} alt="" aria-hidden style={{ display: "none" }} />
        )}
        {hasNext && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl(id, pageNum + 1)} alt="" aria-hidden style={{ display: "none" }} />
        )}

        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Tabs value={activeTab} onChange={(_, v) => setTab(v)} aria-label="Page content">
            <Tab label="Summary" />
            <Tab label="Structured" />
            <Tab label="Raw text" />
          </Tabs>
          {activeTab === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>
              {page.page_summary ?? "No summary available."}
            </Typography>
          )}
          {activeTab === 1 && <JsonViewer data={structured_json} />}
          {activeTab === 2 && (
            <Paper variant="outlined" sx={{ p: 1, maxHeight: "40vh", overflow: "auto" }}>
              <Typography
                component="pre"
                variant="body2"
                sx={{ fontFamily: "var(--font-mono)", whiteSpace: "pre-wrap", m: 0 }}
              >
                {raw_text ?? "—"}
              </Typography>
            </Paper>
          )}
        </Box>
      </Box>
    </Box>
  );
}
