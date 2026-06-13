"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type ActionBarCtx = {
  content: ReactNode;
  setContent: (node: ReactNode) => void;
};

const ActionBarContext = createContext<ActionBarCtx | null>(null);

export function ActionBarProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<ReactNode>(null);
  return <ActionBarContext.Provider value={{ content, setContent }}>{children}</ActionBarContext.Provider>;
}

function useActionBarCtx(): ActionBarCtx {
  const ctx = useContext(ActionBarContext);
  if (!ctx) throw new Error("Action bar hooks must be used within ActionBarProvider");
  return ctx;
}

/** Read the current contextual action-bar content (used by AppShell). */
export function useActionBarContent(): ReactNode {
  return useActionBarCtx().content;
}

/**
 * Publish contextual action-bar content for as long as the calling
 * component is mounted. Pass `null` to clear without unmounting.
 */
export function useSetActionBar(node: ReactNode): void {
  const { setContent } = useActionBarCtx();
  useEffect(() => {
    setContent(node);
    return () => setContent(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node]);
}
