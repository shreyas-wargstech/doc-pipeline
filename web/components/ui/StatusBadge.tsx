import { Badge } from "./Badge";
import type { DocStatus } from "@/lib/types";

const tone: Record<DocStatus, "ok" | "warn" | "danger" | "info" | "muted"> = {
  processed: "ok", processing: "warn", failed: "danger", manual_review: "info", received: "muted",
};
const label: Record<DocStatus, string> = {
  processed: "Processed", processing: "Processing", failed: "Failed",
  manual_review: "Manual review", received: "Received",
};

export function StatusBadge({ status }: { status: DocStatus }) {
  return <Badge tone={tone[status]}>{label[status]}</Badge>;
}
