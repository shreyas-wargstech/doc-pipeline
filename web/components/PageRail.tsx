"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { FileText, FileSignature, ReceiptText, BookText, FileImage } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";
import { titleCase } from "@/lib/format";
import type { OcrStatus, PageRow } from "@/lib/types";

const OCR_DOT_CLASS: Record<OcrStatus, string> = {
  done: "bg-success",
  queued: "bg-warn",
  pending: "bg-tertiary-fg",
  failed: "bg-danger",
  skipped: "bg-info",
};

function iconFor(pageType: string | null) {
  const t = (pageType ?? "").toLowerCase();
  if (t.includes("form")) return FileSignature;
  if (t.includes("receipt")) return ReceiptText;
  if (t.includes("record") || t.includes("book")) return BookText;
  if (t.includes("cover")) return FileImage;
  return FileText;
}

export function PageRail({
  documentId,
  pages,
  collapsed,
}: {
  documentId: string;
  pages: PageRow[];
  collapsed: boolean;
}) {
  const pathname = usePathname();

  return (
    <TooltipProvider>
      <nav
        aria-label="Document pages"
        className="hidden flex-shrink-0 border-r border-border sm:block"
        style={{ width: collapsed ? 56 : 200 }}
      >
        <ScrollArea className="h-[calc(100dvh-56px)]">
          {!collapsed && (
            <div className="px-3 pt-3 pb-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Pages · {pages.length}
            </div>
          )}
          <div className="flex flex-col">
            {pages.map((p) => {
              const href = `/documents/${documentId}/pages/${p.page_num}`;
              const active = pathname === href;
              const Icon = iconFor(p.page_type);
              const label = p.page_type ? titleCase(p.page_type) : `Page ${p.page_num}`;
              return (
                <Tooltip key={p.page_id} delayDuration={0}>
                  <TooltipTrigger asChild>
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      aria-label={label}
                      className={`
                        flex items-center gap-2 border-b border-border px-3 py-2.5 text-sm transition-colors duration-150
                        ${active ? "bg-primary-tint text-primary" : "text-foreground hover:bg-surface-hover"}
                        ${collapsed ? "justify-center" : "justify-start"}
                      `}
                    >
                      <span className={active ? "text-primary" : "text-muted-foreground"}>
                        <Icon className="h-4 w-4" />
                      </span>
                      {!collapsed && (
                        <>
                          <span className="flex-1 truncate">{label}</span>
                          <span
                            role="img"
                            aria-label={`OCR ${p.ocr_status}`}
                            className={`h-2 w-2 flex-shrink-0 rounded-full ${OCR_DOT_CLASS[p.ocr_status]}`}
                          />
                        </>
                      )}
                    </Link>
                  </TooltipTrigger>
                  {collapsed && <TooltipContent side="right">{label}</TooltipContent>}
                </Tooltip>
              );
            })}
          </div>
        </ScrollArea>
      </nav>
    </TooltipProvider>
  );
}
