"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Box from "@mui/material/Box";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Tooltip from "@mui/material/Tooltip";
import { FileText, FileSignature, ReceiptText, BookText, FileImage } from "lucide-react";
import { titleCase } from "@/lib/format";
import type { OcrStatus, PageRow } from "@/lib/types";

const OCR_DOT_COLOR: Record<OcrStatus, string> = {
  done: "success.main",
  queued: "warning.main",
  pending: "text.disabled",
  failed: "error.main",
  skipped: "info.main",
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
    <Box
      component="nav"
      aria-label="Document pages"
      sx={{
        width: collapsed ? 56 : 200,
        flexShrink: 0,
        display: { xs: "none", sm: "block" },
        borderRight: 1,
        borderColor: "divider",
        overflowY: "auto",
        transition: (theme) =>
          theme.transitions.create("width", { duration: theme.transitions.duration.shorter }),
      }}
    >
      {!collapsed && (
        <Box
          sx={{
            px: 1.5,
            pt: 1.5,
            pb: 0.5,
            fontSize: 11,
            letterSpacing: ".05em",
            textTransform: "uppercase",
            color: "text.secondary",
            fontFamily: "var(--font-mono)",
          }}
        >
          Pages · {pages.length}
        </Box>
      )}
      <List dense disablePadding>
        {pages.map((p) => {
          const href = `/documents/${documentId}/pages/${p.page_num}`;
          const active = pathname === href;
          const Icon = iconFor(p.page_type);
          const label = p.page_type ? titleCase(p.page_type) : `Page ${p.page_num}`;
          return (
            <Tooltip key={p.page_id} title={collapsed ? label : ""} placement="right">
              <ListItemButton
                component={Link}
                href={href}
                selected={active}
                aria-current={active ? "page" : undefined}
                aria-label={label}
                sx={{ gap: 1, py: 1, justifyContent: collapsed ? "center" : "flex-start" }}
              >
                <Box sx={{ display: "flex", color: active ? "primary.main" : "text.secondary", flexShrink: 0 }}>
                  <Icon size={16} />
                </Box>
                {!collapsed && (
                  <>
                    <ListItemText
                      primary={label}
                      slotProps={{ primary: { variant: "body2", noWrap: true } }}
                    />
                    <Box
                      component="span"
                      role="img"
                      aria-label={`OCR ${p.ocr_status}`}
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        bgcolor: OCR_DOT_COLOR[p.ocr_status],
                        flexShrink: 0,
                      }}
                    />
                  </>
                )}
              </ListItemButton>
            </Tooltip>
          );
        })}
      </List>
    </Box>
  );
}
