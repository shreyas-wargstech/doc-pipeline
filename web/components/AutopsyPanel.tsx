"use client";

import { motion } from "motion/react";
import { AlertTriangle, CheckCircle2, XCircle, Info, HelpCircle, FileSearch } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAutopsy } from "@/hooks/useEngineRoom";
import type { AutopsyStage, AutopsyReport } from "@/lib/types";
import { cn } from "@/lib/utils";

function stageTone(status: string): "ok" | "warn" | "danger" | "info" | "muted" {
  if (status === "success") return "ok";
  if (status === "partial") return "warn";
  if (status === "failed") return "danger";
  if (status === "manual_review") return "info";
  return "muted";
}

function StageIcon({ status }: { status: string }) {
  if (status === "success") return <CheckCircle2 className="h-4 w-4 text-ok shrink-0" />;
  if (status === "failed") return <XCircle className="h-4 w-4 text-danger shrink-0" />;
  if (status === "partial") return <AlertTriangle className="h-4 w-4 text-warn shrink-0" />;
  if (status === "manual_review") return <FileSearch className="h-4 w-4 text-info shrink-0" />;
  return <HelpCircle className="h-4 w-4 text-muted-fg shrink-0" />;
}

function StageRow({ stage, index }: { stage: AutopsyStage; index: number }) {
  const tone = stageTone(stage.status);
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.06, duration: 0.25, ease: "easeOut" }}
      className={cn(
        "flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors hover:bg-surface-hover",
        tone === "ok" && "border-ok/20",
        tone === "warn" && "border-warn/20",
        tone === "danger" && "border-danger/20",
        tone === "info" && "border-info/20",
        tone === "muted" && "border-border"
      )}
    >
      <div className="mt-0.5">
        <StageIcon status={stage.status} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium capitalize">{stage.name}</span>
          <Badge tone={tone}>{stage.status.replace("_", " ")}</Badge>
        </div>
        <p className="text-xs text-muted-fg mt-1 leading-relaxed">{stage.detail}</p>
        {stage.duration_sec !== undefined && stage.duration_sec !== null && (
          <p className="text-xs text-muted-fg mt-0.5">{stage.duration_sec.toFixed(1)}s</p>
        )}
      </div>
    </motion.div>
  );
}

export function AutopsyPanel({ documentId }: { documentId: string }) {
  const autopsy = useAutopsy(documentId);

  if (autopsy.isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-3/4" />
      </div>
    );
  }

  if (autopsy.isError || !autopsy.data) {
    return (
      <p className="text-sm text-muted-fg">
        Autopsy unavailable. The document may not have pipeline data yet.
      </p>
    );
  }

  const report: AutopsyReport = autopsy.data;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    >
      <Card className="border">
        <CardHeader>
          <div className="flex items-center gap-2">
            <CardTitle className="text-base font-semibold">Document Autopsy</CardTitle>
            <Badge tone={stageTone(report.overall_status)}>
              {report.overall_status.replace("_", " ")}
            </Badge>
          </div>
          <CardDescription>
            Stage-by-stage breakdown of why this document reached its current state.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {report.stages.map((stage, i) => (
            <StageRow key={stage.name} stage={stage} index={i} />
          ))}

          {report.recommendation && (
            <motion.div
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.3 }}
              className="mt-3 rounded-lg border border-secondary/20 bg-secondary-tint p-3"
            >
              <div className="flex items-start gap-2">
                <Info className="h-4 w-4 text-secondary shrink-0 mt-0.5" />
                <p className="text-sm text-foreground">{report.recommendation}</p>
              </div>
            </motion.div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
