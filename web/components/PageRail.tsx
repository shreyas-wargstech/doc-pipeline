"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Box from "@mui/material/Box";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import { imageUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { OcrStatus, PageRow } from "@/lib/types";

const OCR_DOT_COLOR: Record<OcrStatus, string> = {
  done: "success.main",
  queued: "warning.main",
  pending: "text.disabled",
  failed: "error.main",
  skipped: "info.main",
};

export function PageRail({ documentId, pages }: { documentId: string; pages: PageRow[] }) {
  const pathname = usePathname();

  return (
    <Box
      component="nav"
      aria-label="Document pages"
      sx={{
        width: 160,
        flexShrink: 0,
        display: { xs: "none", sm: "block" },
        borderRight: 1,
        borderColor: "divider",
        overflowY: "auto",
      }}
    >
      <List dense disablePadding>
        {pages.map((p) => {
          const href = `/documents/${documentId}/pages/${p.page_num}`;
          const active = pathname === href;
          return (
            <ListItemButton
              key={p.page_id}
              component={Link}
              href={href}
              selected={active}
              aria-current={active ? "page" : undefined}
              sx={{ alignItems: "flex-start", gap: 1, py: 1 }}
            >
              <Box
                component="img"
                src={imageUrl(documentId, p.page_num)}
                alt={`Page ${p.page_num} thumbnail`}
                loading="lazy"
                sx={{ width: 40, height: 53, objectFit: "cover", borderRadius: 0.5, flexShrink: 0, bgcolor: "action.hover" }}
              />
              <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                <ListItemText
                  primary={`Page ${p.page_num}`}
                  secondary={titleCase(p.page_type)}
                  slotProps={{
                    primary: { variant: "body2" },
                    secondary: { variant: "caption", noWrap: true },
                  }}
                />
                <Box
                  component="span"
                  role="img"
                  aria-label={`OCR ${p.ocr_status}`}
                  sx={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", bgcolor: OCR_DOT_COLOR[p.ocr_status] }}
                />
              </Box>
            </ListItemButton>
          );
        })}
      </List>
    </Box>
  );
}
