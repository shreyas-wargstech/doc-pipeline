"use client";
import { Bookmark } from "lucide-react";
import { useEffect, useState } from "react";
import IconButton from "@mui/material/IconButton";
import { useToggleBookmark } from "@/hooks/useBookmarks";

/**
 * Per-user bookmark toggle. Optimistic: flips local state immediately, fires the
 * mutation, and reverts on error. Stops click propagation so it can sit inside a
 * clickable table row without triggering navigation.
 */
export function BookmarkStar({
  documentId,
  bookmarked,
}: {
  documentId: string;
  bookmarked: boolean;
}) {
  const [on, setOn] = useState(bookmarked);
  useEffect(() => setOn(bookmarked), [bookmarked]);
  const toggle = useToggleBookmark(documentId);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    const next = !on;
    setOn(next);
    toggle.mutate(next, { onError: () => setOn(!next) });
  };

  return (
    <IconButton
      size="small"
      aria-label={on ? "Remove bookmark" : "Add bookmark"}
      aria-pressed={on}
      onClick={handleClick}
      color={on ? "primary" : "default"}
    >
      <Bookmark className="h-4 w-4" fill={on ? "currentColor" : "none"} />
    </IconButton>
  );
}
