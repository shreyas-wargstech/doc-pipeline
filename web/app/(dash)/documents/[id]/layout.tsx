"use client";
import { createContext, use, useContext } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import MenuOpenIcon from "@mui/icons-material/MenuOpen";
import MenuIcon from "@mui/icons-material/Menu";
import { PageRail } from "@/components/PageRail";
import { Skeleton } from "@/components/ui/Skeleton";
import { useDocument } from "@/hooks/useDocument";
import { useCollapsible } from "@/hooks/useCollapsible";

type RailCtx = { collapsed: boolean; toggle: () => void };
const RailContext = createContext<RailCtx | null>(null);

/** Used by the page viewer header to toggle the shared page rail. */
export function usePageRail(): RailCtx {
  const ctx = useContext(RailContext);
  if (!ctx) return { collapsed: false, toggle: () => {} };
  return ctx;
}

/** Standalone toggle button for the page rail (rendered in the viewer header). */
export function PageRailToggle() {
  const { collapsed, toggle } = usePageRail();
  return (
    <IconButton
      onClick={toggle}
      size="small"
      aria-label={collapsed ? "Show page list" : "Hide page list"}
      color={collapsed ? "default" : "primary"}
    >
      {collapsed ? <MenuIcon fontSize="small" /> : <MenuOpenIcon fontSize="small" />}
    </IconButton>
  );
}

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
      <Box sx={{ display: "flex", gap: 2 }}>
        {q.isLoading ? (
          <Stack spacing={1} sx={{ width: rail.collapsed ? 56 : 200, flexShrink: 0, display: { xs: "none", sm: "flex" } }}>
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </Stack>
        ) : q.data ? (
          <PageRail documentId={id} pages={q.data.pages} collapsed={rail.collapsed} />
        ) : null}
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>{children}</Box>
      </Box>
    </RailContext.Provider>
  );
}
