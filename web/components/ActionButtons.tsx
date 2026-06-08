"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, RotateCcw, Tags } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { apiPost } from "@/lib/api";
import { useToast } from "@/app/providers";
import type { ActionResult } from "@/lib/types";

type ActionKey = "ingest" | "requeue-ocr" | "reclassify";

export function ActionButtons({ documentId }: { documentId: string }) {
  const qc = useQueryClient();
  const { push } = useToast();
  const [pending, setPending] = useState<ActionKey | null>(null);

  const run = useMutation({
    mutationFn: (key: ActionKey) => apiPost<ActionResult>(`/api/documents/${documentId}/${key}`),
    onSuccess: (res) => {
      push(res.ok ? "ok" : "error", res.message);
      qc.invalidateQueries({ queryKey: ["document", documentId] });
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: () => push("error", "Request failed."),
    onSettled: () => setPending(null),
  });

  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" onClick={() => setPending("ingest")}><RefreshCw className="h-4 w-4" />Re-ingest</Button>
      <Button variant="secondary" onClick={() => run.mutate("requeue-ocr")} loading={run.isPending && run.variables === "requeue-ocr"}>
        <RotateCcw className="h-4 w-4" />Requeue OCR
      </Button>
      <Button variant="secondary" onClick={() => run.mutate("reclassify")} loading={run.isPending && run.variables === "reclassify"}>
        <Tags className="h-4 w-4" />Re-classify
      </Button>

      <ConfirmDialog
        open={pending === "ingest"}
        title="Re-ingest this document?"
        body="Re-runs the ingest stage from the stored manifest. Idempotent, but re-drives downstream work."
        confirmLabel="Re-ingest"
        loading={run.isPending}
        onCancel={() => setPending(null)}
        onConfirm={() => run.mutate("ingest")}
      />
    </div>
  );
}
