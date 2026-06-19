"use client";

import { useState } from "react";
import { motion } from "motion/react";
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Wrench,
  Search,
  Play,
  Save,
  FlaskConical,
  DollarSign,
  Loader2,
} from "lucide-react";

import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { KpiCard } from "@/components/KpiCard";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/Dialog";
import {
  useEngineHealth,
  useEngineDiagnostics,
  useEngineParameters,
  useEngineTuningSuggestions,
  useUpdateParameter,
  useTestParameter,
  useEngineABTest,
  useEngineCostSummary,
  useEngineInspector,
} from "@/hooks/useEngineRoom";
import { cn } from "@/lib/utils";
import type { HealthCheck, TuningSuggestion } from "@/lib/types";

/* ------------------------------------------------------------------ */
/*  Health                                                            */
/* ------------------------------------------------------------------ */

function statusTone(status: string): "ok" | "warn" | "danger" | "muted" {
  if (status === "ok") return "ok";
  if (status === "warn") return "warn";
  if (status === "error") return "danger";
  return "muted";
}

function HealthCard({ check, index }: { check: HealthCheck; index: number }) {
  const tone = statusTone(check.status);
  const Icon = tone === "ok" ? CheckCircle2 : tone === "warn" ? AlertTriangle : XCircle;
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.3, ease: "easeOut" }}
    >
      <Card className="border hover:shadow-md transition-shadow duration-200">
        <CardContent className="flex items-start gap-3 p-4">
          <div className={cn("mt-0.5", tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : "text-danger")}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm text-foreground capitalize">{check.name}</span>
              <Badge tone={tone}>{check.status}</Badge>
            </div>
            <p className="text-xs text-muted-fg mt-1">{check.detail}</p>
            {check.latency_ms !== undefined && (
              <p className="text-xs text-muted-fg mt-0.5">{check.latency_ms}ms</p>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Diagnostics                                                       */
/* ------------------------------------------------------------------ */

function DiagnosticsPanel() {
  const [expanded, setExpanded] = useState(false);
  const diag = useEngineDiagnostics();

  const results = diag.data?.results ?? [];

  return (
    <Card className="border">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div>
          <CardTitle className="text-base font-semibold">Diagnostics</CardTitle>
          <CardDescription>Run integrity checks across the pipeline.</CardDescription>
        </div>
        <Button
          loading={diag.isFetching}
          onClick={() => {
            diag.refetch();
            setExpanded(true);
          }}
        >
          <Play className="h-4 w-4 mr-1" />
          Run checks
        </Button>
      </CardHeader>
      <CardContent>
        {diag.isLoading && !diag.isFetching && (
          <p className="text-sm text-muted-fg">Click "Run checks" to start.</p>
        )}
        {diag.isFetching && (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-3/4" />
          </div>
        )}
        {!diag.isFetching && results.length > 0 && (
          <div className="space-y-2">
            {results.map((r, i) => (
              <motion.div
                key={r.name}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 border",
                  r.passed
                    ? "border-ok/20 bg-ok-bg"
                    : r.severity === "error"
                    ? "border-danger/20 bg-danger-bg"
                    : "border-warn/20 bg-warn-bg"
                )}
              >
                {r.passed ? (
                  <CheckCircle2 className="h-4 w-4 text-ok shrink-0" />
                ) : (
                  <AlertTriangle className="h-4 w-4 text-warn shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{r.name}</p>
                  <p className="text-xs text-muted-fg">{r.detail}</p>
                </div>
                <Badge tone={r.passed ? "ok" : r.severity === "error" ? "danger" : "warn"}>
                  {r.passed ? "pass" : r.severity}
                </Badge>
              </motion.div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Parameter Tuner                                                 */
/* ------------------------------------------------------------------ */

function ParameterTuner() {
  const params = useEngineParameters();
  const suggestions = useEngineTuningSuggestions();
  const update = useUpdateParameter();
  const test = useTestParameter();

  const [editOpen, setEditOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editValue, setEditValue] = useState("");
  const [editReason, setEditReason] = useState("");
  const [testResult, setTestResult] = useState<unknown>(null);

  const entries = Object.entries(params.data ?? {});
  const suggs = suggestions.data?.suggestions ?? [];

  const openEdit = (name: string, current: string) => {
    setEditName(name);
    setEditValue(current);
    setEditReason("");
    setTestResult(null);
    setEditOpen(true);
  };

  const handleTest = async () => {
    const res = await test.mutateAsync({ name: editName, value: editValue, sample_size: 5 });
    setTestResult(res);
  };

  const handleSave = async () => {
    await update.mutateAsync({ name: editName, value: editValue, reason: editReason || undefined });
    setEditOpen(false);
  };

  return (
    <Card className="border">
      <CardHeader>
        <CardTitle className="text-base font-semibold">Parameter Tuner</CardTitle>
        <CardDescription>Adjust pipeline thresholds and review learned suggestions.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {params.isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-3/4" />
          </div>
        )}
        {entries.length > 0 && (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-surface-alt">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-muted-fg">Parameter</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-fg">Value</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-fg">Source</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-fg">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {entries.map(([name, p]) => (
                  <tr key={name} className="hover:bg-surface-hover transition-colors">
                    <td className="px-3 py-2 font-mono text-xs">{name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{p.value}</td>
                    <td className="px-3 py-2">
                      <Badge tone={p.source === "database" ? "primary" : "muted"}>{p.source}</Badge>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button variant="ghost" size="sm" onClick={() => openEdit(name, p.value)}>
                        <Wrench className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {suggs.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold">Suggested changes</h4>
            {suggs.map((s: TuningSuggestion) => (
              <div
                key={s.parameter}
                className="flex items-center justify-between rounded-lg border border-secondary/20 bg-secondary-tint px-3 py-2"
              >
                <div>
                  <p className="text-sm font-medium">
                    {s.parameter}: <span className="font-mono">{s.current_value}</span> →{" "}
                    <span className="font-mono">{s.suggested_value}</span>
                  </p>
                  <p className="text-xs text-muted-fg">{s.reason}</p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => openEdit(s.parameter, s.suggested_value)}
                >
                  Apply
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit {editName}</DialogTitle>
            <DialogDescription>Test on a sample before saving.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-muted-fg">Value</label>
              <Input value={editValue} onChange={(e) => setEditValue(e.target.value)} />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-fg">Reason (optional)</label>
              <Input value={editReason} onChange={(e) => setEditReason(e.target.value)} />
            </div>
            {testResult !== null && testResult !== undefined && (
              <div className="rounded-lg border bg-surface-alt p-3 text-xs font-mono overflow-auto max-h-40">
                <pre>{JSON.stringify(testResult, null, 2)}</pre>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button loading={test.isPending} variant="secondary" onClick={handleTest}>
              <FlaskConical className="h-4 w-4 mr-1" />
              Test
            </Button>
            <Button loading={update.isPending} onClick={handleSave}>
              <Save className="h-4 w-4 mr-1" />
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  A/B Test                                                        */
/* ------------------------------------------------------------------ */

function ABTestPanel() {
  const ab = useEngineABTest();
  const [hypothesis, setHypothesis] = useState("");
  const [sampleSize, setSampleSize] = useState(10);
  const [variantJson, setVariantJson] = useState("{}");

  return (
    <Card className="border">
      <CardHeader>
        <CardTitle className="text-base font-semibold">A / B Test</CardTitle>
        <CardDescription>Compare baseline vs a variant configuration on a sample.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="text-xs font-medium text-muted-fg">Hypothesis</label>
            <Input
              placeholder="e.g. Lower OCR confidence threshold..."
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-fg">Sample size</label>
            <Input
              type="number"
              min={1}
              max={50}
              value={sampleSize}
              onChange={(e) => setSampleSize(Number(e.target.value))}
            />
          </div>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-fg">Variant JSON</label>
          <textarea
            className="w-full rounded-base border border-input bg-background px-3 py-2 text-sm font-mono min-h-[80px]"
            value={variantJson}
            onChange={(e) => setVariantJson(e.target.value)}
          />
        </div>
        <Button
          loading={ab.isPending}
          disabled={!hypothesis}
          onClick={async () => {
            let variant: Record<string, unknown>;
            try {
              variant = JSON.parse(variantJson);
            } catch {
              alert("Invalid JSON in variant");
              return;
            }
            await ab.mutateAsync({ hypothesis, sample_size: sampleSize, variant });
          }}
        >
          <FlaskConical className="h-4 w-4 mr-1" />
          Run test
        </Button>

        {ab.data && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-lg border bg-surface-alt p-4 space-y-2"
          >
            <div className="flex items-center gap-2">
              <Badge tone={ab.data.winner === "variant" ? "ok" : ab.data.winner === "tie" ? "info" : "muted"}>
                {ab.data.winner} wins
              </Badge>
              {ab.data.improvement_pct !== null && (
                <span className="text-sm font-medium">
                  {ab.data.improvement_pct > 0 ? "+" : ""}
                  {ab.data.improvement_pct.toFixed(1)}%
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="rounded border p-2">
                <p className="font-medium text-muted-fg mb-1">Baseline</p>
                <pre className="overflow-auto max-h-32">
                  {JSON.stringify(ab.data.baseline, null, 2)}
                </pre>
              </div>
              <div className="rounded border p-2">
                <p className="font-medium text-muted-fg mb-1">Variant</p>
                <pre className="overflow-auto max-h-32">
                  {JSON.stringify(ab.data.variant, null, 2)}
                </pre>
              </div>
            </div>
          </motion.div>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Cost Summary                                                    */
/* ------------------------------------------------------------------ */

function CostSummaryPanel() {
  const cost = useEngineCostSummary();
  const summary = cost.data;

  return (
    <Card className="border">
      <CardHeader>
        <CardTitle className="text-base font-semibold">Cost Summary</CardTitle>
        <CardDescription>Per-run and aggregate pipeline spend.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {cost.isLoading && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        )}
        {summary && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <KpiCard label="Total cost" value={`$${(summary.total_cost ?? 0).toFixed(4)}`} />
              <KpiCard label="Runs" value={summary.total_runs} />
              <KpiCard label="Avg / run" value={`$${(summary.avg_cost_per_run ?? 0).toFixed(4)}`} />
              <KpiCard label="Avg / page" value={`$${(summary.avg_cost_per_page ?? 0).toFixed(4)}`} />
            </div>
            {Object.keys(summary.per_stage).length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-muted-fg uppercase tracking-wider mb-2">
                  Per stage
                </h4>
                <div className="space-y-1">
                  {Object.entries(summary.per_stage).map(([stage, amount]) => (
                    <div
                      key={stage}
                      className="flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-surface-hover transition-colors"
                    >
                      <span className="text-sm capitalize">{stage}</span>
                      <span className="text-sm font-mono">${amount.toFixed(4)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Document Inspector                                              */
/* ------------------------------------------------------------------ */

function DocumentInspector() {
  const [docId, setDocId] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const inspector = useEngineInspector(activeId);

  const run = () => setActiveId(docId.trim() || null);

  return (
    <Card className="border">
      <CardHeader>
        <CardTitle className="text-base font-semibold">Document Inspector</CardTitle>
        <CardDescription>Inspect a document's pipeline stage-by-stage.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input
            placeholder="document_id"
            className="font-mono"
            value={docId}
            onChange={(e) => setDocId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
          />
          <Button onClick={run} loading={inspector.isFetching}>
            <Search className="h-4 w-4 mr-1" />
            Inspect
          </Button>
        </div>

        {inspector.isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-3/4" />
          </div>
        )}

        {inspector.data && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="space-y-2"
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs">{inspector.data.document_id}</span>
              <Badge tone={inspector.data.overall_status === "processed" ? "ok" : "warn"}>
                {inspector.data.overall_status}
              </Badge>
            </div>
            <div className="space-y-1">
              {inspector.data.stages.map((stage, i) => (
                <motion.div
                  key={stage.stage}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="flex items-center gap-2 rounded-md px-2 py-1.5 border border-border hover:bg-surface-hover transition-colors"
                >
                  <div className="w-2 h-2 rounded-full shrink-0"
                    style={{
                      background:
                        stage.status === "success"
                          ? "var(--color-ok)"
                          : stage.status === "failed"
                          ? "var(--color-danger)"
                          : stage.status === "pending"
                          ? "var(--color-tertiary-fg)"
                          : "var(--color-warn)",
                    }}
                  />
                  <span className="text-sm font-medium w-24 shrink-0">{stage.stage}</span>
                  <span className="text-sm text-muted-fg flex-1 truncate">{stage.detail}</span>
                  <Badge tone={stage.status === "success" ? "ok" : stage.status === "failed" ? "danger" : "warn"}>
                    {stage.status}
                  </Badge>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                            */
/* ------------------------------------------------------------------ */

export default function EngineRoomPage() {
  const health = useEngineHealth();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Engine Room"
        subtitle="System health, tuning controls, and pipeline diagnostics."
      />

      {/* Health */}
      <section className="space-y-3">
        <h2 className="font-display text-lg font-semibold text-foreground flex items-center gap-2">
          <Activity className="h-5 w-5 text-primary" />
          Health
        </h2>
        {health.isLoading && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </div>
        )}
        {health.data && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {(health.data.checks ?? []).map((check, i) => (
              <HealthCard key={check.name} check={check} index={i} />
            ))}
          </div>
        )}
      </section>

      {/* Inspector + Diagnostics */}
      <div className="grid gap-4 lg:grid-cols-2">
        <DocumentInspector />
        <DiagnosticsPanel />
      </div>

      {/* Tuner + A/B Test */}
      <div className="grid gap-4 lg:grid-cols-2">
        <ParameterTuner />
        <ABTestPanel />
      </div>

      {/* Cost */}
      <CostSummaryPanel />

      <p className="text-xs text-muted-fg">
        Engine Room v1 — live parameters, A/B testing, and cost tracking.
      </p>
    </div>
  );
}
