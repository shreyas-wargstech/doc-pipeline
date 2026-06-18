"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  Maximize,
  PanelLeft,
  PanelRight,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import { JsonViewer } from "@/components/JsonViewer";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { PageRailToggle } from "@/components/PageRailContext";
import { imageUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { useDocument } from "@/hooks/useDocument";
import { usePage } from "@/hooks/usePage";
import { useCollapsible } from "@/hooks/useCollapsible";
import { useToast } from "@/app/providers";

type ZoomRef = {
  zoomIn: () => void;
  zoomOut: () => void;
  resetTransform: () => void;
};

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
  const dataPanel = useCollapsible("page-data-panel", false);
  const zoomRef = useRef<ZoomRef>({ zoomIn: () => {}, zoomOut: () => {}, resetTransform: () => {} });

  const pageCount = docQuery.data?.doc?.page_count ?? null;
  const hasPrev = pageNum > 1;
  const hasNext = pageCount != null && pageNum < pageCount;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft" && hasPrev) {
        router.push(`/documents/${id}/pages/${pageNum - 1}`);
      }
      if (e.key === "ArrowRight" && hasNext) {
        router.push(`/documents/${id}/pages/${pageNum + 1}`);
      }
      if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        zoomRef.current.zoomIn();
      }
      if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        zoomRef.current.zoomOut();
      }
      if (e.key === "0") {
        e.preventDefault();
        zoomRef.current.resetTransform();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [id, pageNum, hasPrev, hasNext, router]);

  if (!resolved || q.isLoading) return <Skeleton className="h-96 w-full" />;
  if (q.isError || !q.data) return <p className="text-sm text-danger">Failed to load page.</p>;
  const { page, structured_json, raw_text } = q.data;

  const defaultTab = page.page_summary ? 0 : 1;
  const activeTab = tab ?? defaultTab;

  const copyLink = async () => {
    await navigator.clipboard.writeText(window.location.href);
    pushToast("ok", "Link copied to clipboard");
  };

  const imgAlt = [
    `Page ${pageNum}`,
    page.page_type ? `— ${titleCase(page.page_type)}` : "",
    page.ocr_status === "done" ? "OCR complete" : "OCR pending",
    page.confidence_score != null ? `confidence ${page.confidence_score.toFixed(0)}%` : "",
  ].filter(Boolean).join(". ");

  const tabs = [
    { label: "Summary", content: page.page_summary ?? "No summary available." },
    { label: "Structured", content: <JsonViewer data={structured_json} /> },
    { label: "Raw text", content: raw_text ?? "—" },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 bg-background/80 py-2 backdrop-blur-md">
        <PageRailToggle />
        <Button
          variant="ghost"
          size="icon"
          asChild
          aria-label="Previous page"
          aria-disabled={!hasPrev}
          tabIndex={hasPrev ? undefined : -1}
        >
          <Link
            href={hasPrev ? `/documents/${id}/pages/${pageNum - 1}` : `/documents/${id}/pages/${pageNum}`}
            onClick={(e) => {
              if (!hasPrev) e.preventDefault();
            }}
          >
            <ChevronLeft className="h-4 w-4" />
          </Link>
        </Button>
        <h1 className="font-display text-lg font-semibold text-foreground">Page {page.page_num}</h1>
        <Button
          variant="ghost"
          size="icon"
          asChild
          aria-label="Next page"
          aria-disabled={!hasNext}
          tabIndex={hasNext ? undefined : -1}
        >
          <Link
            href={hasNext ? `/documents/${id}/pages/${pageNum + 1}` : `/documents/${id}/pages/${pageNum}`}
            onClick={(e) => {
              if (!hasNext) e.preventDefault();
            }}
          >
            <ChevronRight className="h-4 w-4" />
          </Link>
        </Button>

        <Badge tone="secondary">{titleCase(page.page_type)}</Badge>
        <Badge tone={page.ocr_status === "done" ? "ok" : "warn"}>{page.ocr_status}</Badge>
        {page.language_detected && <Badge tone="info">{page.language_detected}</Badge>}
        {page.confidence_score != null && (
          <span className="tnum text-xs text-muted-foreground">
            conf {page.confidence_score.toFixed(0)}
          </span>
        )}

        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="icon" aria-label="Copy link" onClick={copyLink}>
            <Copy className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={dataPanel.collapsed ? "Show data panel" : "Hide data panel"}
            onClick={dataPanel.toggle}
            className={dataPanel.collapsed ? "text-muted-foreground" : "text-primary"}
          >
            {dataPanel.collapsed ? <PanelLeft className="h-4 w-4" /> : <PanelRight className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: dataPanel.collapsed ? "1fr" : "1fr 1fr" }}
      >
        <div className="overflow-hidden rounded-panel border border-border relative bg-surface">
          <TransformWrapper
            key={pageNum}
            minScale={1}
            maxScale={6}
            doubleClick={{ disabled: false, mode: "reset" }}
            wheel={{ step: 0.15 }}
          >
            {({ zoomIn, zoomOut, resetTransform }) => {
              zoomRef.current = { zoomIn, zoomOut, resetTransform };
              return (
                <>
                  <TransformComponent
                    wrapperStyle={{ width: "100%" }}
                    contentStyle={{ width: "100%" }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={imageUrl(id, pageNum)} alt={imgAlt} style={{ width: "100%", display: "block" }} />
                  </TransformComponent>
                  <div className="absolute right-2 bottom-2 z-20 flex flex-col gap-1">
                    <Button variant="secondary" size="icon" aria-label="Zoom in (plus key)" onClick={() => zoomIn()} className="bg-surface shadow-md">
                      <ZoomIn className="h-4 w-4" />
                    </Button>
                    <Button variant="secondary" size="icon" aria-label="Zoom out (minus key)" onClick={() => zoomOut()} className="bg-surface shadow-md">
                      <ZoomOut className="h-4 w-4" />
                    </Button>
                    <Button variant="secondary" size="icon" aria-label="Fit to width (zero key)" onClick={() => resetTransform()} className="bg-surface shadow-md">
                      <Maximize className="h-4 w-4" />
                    </Button>
                  </div>
                </>
              );
            }}
          </TransformWrapper>
        </div>

        {hasPrev && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl(id, pageNum - 1)} alt="" aria-hidden style={{ display: "none" }} />
        )}
        {hasNext && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl(id, pageNum + 1)} alt="" aria-hidden style={{ display: "none" }} />
        )}

        <AnimatePresence>
          {!dataPanel.collapsed && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="flex flex-col gap-2"
            >
              <div className="flex gap-1 border-b border-border" role="tablist">
                {tabs.map((t, i) => (
                  <button
                    key={t.label}
                    role="tab"
                    aria-selected={activeTab === i}
                    onClick={() => setTab(i)}
                    className={`
                      px-3 py-2 text-sm font-medium transition-colors duration-150
                      ${activeTab === i ? "border-b-2 border-primary text-primary" : "text-muted-foreground hover:text-foreground"}
                    `}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="min-h-0 flex-1 overflow-auto rounded-panel border border-border p-3">
                {activeTab === 0 && (
                  <p className="text-sm text-muted-foreground">{tabs[0].content}</p>
                )}
                {activeTab === 1 && tabs[1].content}
                {activeTab === 2 && (
                  <pre className="font-mono text-sm whitespace-pre-wrap text-foreground">
                    {tabs[2].content}
                  </pre>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
