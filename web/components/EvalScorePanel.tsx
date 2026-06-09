"use client";
import { useEvalScore, useEvalSweep } from "@/hooks/useEval";
import { Card } from "@/components/ui/Card";

function pct(x: number): string { return `${(x * 100).toFixed(1)}%`; }

export function EvalScorePanel() {
  const score = useEvalScore();
  const sweep = useEvalSweep();

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <div className="space-y-2">
          <h3 className="font-medium">Score @ current thresholds</h3>
          {score.data ? (
            <>
              <p className="text-sm">n = {score.data.n} · accuracy {pct(score.data.accuracy)}</p>
              <p className="text-sm">precision {pct(score.data.precision)} · recall {pct(score.data.recall)} · f1 {pct(score.data.f1)}</p>
              <table className="mt-2 text-xs" aria-label="Confusion matrix">
                <tbody>
                  <tr><td className="pr-3">TP (hand→hand)</td><td>{score.data.confusion.tp}</td></tr>
                  <tr><td className="pr-3">FP (typed→hand)</td><td>{score.data.confusion.fp}</td></tr>
                  <tr><td className="pr-3">FN (hand→typed)</td><td>{score.data.confusion.fn}</td></tr>
                  <tr><td className="pr-3">TN (typed→typed)</td><td>{score.data.confusion.tn}</td></tr>
                </tbody>
              </table>
            </>
          ) : <p className="text-sm text-muted-foreground">Label some pages to see a score.</p>}
        </div>
      </Card>
      <Card>
        <div className="space-y-2">
          <h3 className="font-medium">Threshold sweep — recommended</h3>
          {sweep.data ? (
            <>
              <p className="text-sm">
                height_cv ≤ <b>{sweep.data.best.height_cv_threshold}</b> ·
                stroke_cv ≤ <b>{sweep.data.best.stroke_cv_threshold}</b> ·
                weight <b>{sweep.data.best.height_weight}</b>
              </p>
              <p className="text-sm">accuracy {pct(sweep.data.best.accuracy)} · typed-precision {pct(sweep.data.best.typed_precision)}</p>
              <p className="text-xs text-muted-foreground">
                Apply by editing HeuristicContentTypeDetector defaults in nas/preprocess/triage.py (the lab never auto-writes thresholds).
              </p>
            </>
          ) : <p className="text-sm text-muted-foreground">Label some pages to compute a sweep.</p>}
        </div>
      </Card>
    </div>
  );
}
