"use client";

import { createContext, use, useContext } from "react";
import { PanelLeft, PanelRight } from "lucide-react";
import { Button } from "@/components/ui/Button";

type RailCtx = { collapsed: boolean; toggle: () => void };

export const RailContext = createContext<RailCtx | null>(null);

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
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label={collapsed ? "Show page list" : "Hide page list"}
      className={collapsed ? "text-muted-foreground" : "text-primary"}
    >
      {collapsed ? <PanelLeft className="h-4 w-4" /> : <PanelRight className="h-4 w-4" />}
    </Button>
  );
}
