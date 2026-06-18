"use client";
import { Star, StarOff } from "lucide-react";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Button } from "@/components/ui/Button";
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
    <motion.div
      whileTap={{ scale: 0.85 }}
      transition={{ duration: 0.1, ease: "easeOut" }}
    >
      <Button
        variant="ghost"
        size="icon"
        aria-label={on ? "Remove bookmark" : "Add bookmark"}
        aria-pressed={on}
        onClick={handleClick}
        className={on ? "text-primary" : "text-muted-foreground"}
      >
        {on ? <Star className="h-4 w-4 fill-current" /> : <StarOff className="h-4 w-4" />}
      </Button>
    </motion.div>
  );
}
