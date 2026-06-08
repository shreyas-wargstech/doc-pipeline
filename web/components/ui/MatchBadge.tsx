import { Badge } from "./Badge";
import type { MatchStatus } from "@/lib/types";

export function MatchBadge({ status }: { status: MatchStatus }) {
  if (status === null) return <span className="text-muted-fg">—</span>;
  const tone = { matched: "ok", unmatched: "danger", not_applicable: "muted", manual_review: "info" } as const;
  const label = { matched: "Matched", unmatched: "Unmatched", not_applicable: "N/A", manual_review: "Review" };
  return <Badge tone={tone[status]}>{label[status]}</Badge>;
}
