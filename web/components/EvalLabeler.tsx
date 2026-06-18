"use client";
import { useEffect, useReducer } from "react";
import { evalReducer, initialEvalState, type EvalLabel, type EvalPage } from "@/lib/eval-reducer";
import { imageUrl } from "@/lib/api";
import { useSetLabel } from "@/hooks/useEval";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Badge } from "@/components/ui/Badge";

// Display-only prediction mirroring the detector defaults (0.35 / 0.45 / weight 0.5).
// Authoritative prediction is server-side scoring; this is just a labeling aid.
function prediction(p: EvalPage): string {
  if (p.height_cv == null || p.stroke_cv == null) return "—";
  if ((p.n_components ?? 0) < 12) return "unknown";
  const score = 0.5 * (p.height_cv / 0.35) + 0.5 * (p.stroke_cv / 0.45);
  return score >= 1 ? "handwritten" : "typed";
}

export function EvalLabeler({ pages }: { pages: EvalPage[] }) {
  const [state, dispatch] = useReducer(evalReducer, initialEvalState);
  const setLabel = useSetLabel();

  useEffect(() => { dispatch({ type: "load", pages }); }, [pages]);

  const page = state.pages[state.cursor];

  function apply(label: EvalLabel) {
    if (!page) return;
    setLabel.mutate({ pageId: page.page_id, label });
    dispatch({ type: "label", page_id: page.page_id, label });
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "t") apply("typed");
      else if (e.key === "h") apply("handwritten");
      else if (e.key === "s" || e.key === "ArrowRight") dispatch({ type: "skip" });
      else if (e.key === "ArrowLeft") dispatch({ type: "goto", cursor: state.cursor - 1 });
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!page) return (
    <Card>
      <p className="text-sm text-muted-fg">No enrolled pages. Enrol a document above.</p>
    </Card>
  );

  const labeled = state.pages.filter((p) => p.label).length;
  const pred = prediction(page);

  return (
    <Card className="p-0">
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between text-sm">
          <span>{page.document_id} · page {page.page_num}</span>
          <span className="flex items-center gap-1 text-muted-fg">
            predicted: <Badge tone="info">{pred}</Badge>
            {page.label ? <> · labeled: <Badge tone="ok">{page.label}</Badge></> : null}
          </span>
        </div>
        <ProgressBar done={labeled} total={state.pages.length} />
        <div className="flex justify-center bg-muted/30">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imageUrl(page.document_id, page.page_num)}
            alt={`page ${page.page_num}`}
            className="max-h-[60vh] object-contain"
          />
        </div>
        <div className="flex gap-2">
          <Button onClick={() => apply("typed")}>Typed (t)</Button>
          <Button onClick={() => apply("handwritten")}>Handwritten (h)</Button>
          <Button variant="ghost" onClick={() => dispatch({ type: "skip" })}>Skip (s)</Button>
          <span className="ml-auto self-center text-xs text-muted-fg">
            {labeled}/{state.pages.length} labeled
          </span>
        </div>
      </div>
    </Card>
  );
}
