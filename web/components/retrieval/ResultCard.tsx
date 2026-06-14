import type { RetrievalHit } from "@/lib/types";

const TIER: Record<1 | 2 | 3, { label: string; cls: string }> = {
  1: { label: "Keyword", cls: "bg-primary-tint text-primary" },
  2: { label: "Graph", cls: "bg-info-bg text-info" },
  3: { label: "Vector", cls: "bg-surface-alt text-muted-fg" },
};

function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}

export function ResultCard({
  hit,
  selected,
  onClick,
}: {
  hit: RetrievalHit;
  selected: boolean;
  onClick: () => void;
}) {
  const tier = TIER[hit.tier as 1 | 2 | 3] ?? { label: "Unknown", cls: "bg-surface-alt text-muted-fg" };
  const pct = Math.max(0, Math.min(1, hit.score)) * 100;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`flex w-full flex-col gap-1.5 rounded-panel border p-3 text-left transition-shadow ${
        selected
          ? "border-primary shadow-[0_0_0_3px_rgba(13,148,136,0.10)] bg-surface"
          : "border-border bg-surface hover:shadow-sm"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-mono text-xs font-semibold text-foreground">{shortId(hit.document_id)}</div>
          <div className="text-xs text-muted-fg">{hit.document_type ?? "—"}</div>
        </div>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${tier.cls}`}>
          {tier.label}
        </span>
      </div>
      <p className="text-xs italic text-muted-fg">{hit.why_matched}</p>
      <div className="flex items-center gap-1.5">
        <div className="h-[3px] flex-1 overflow-hidden rounded-sm bg-border">
          <div className="h-full rounded-sm bg-primary" style={{ width: `${pct}%` }} />
        </div>
        <span className="font-mono text-[10px] text-tertiary-fg">{hit.score.toFixed(2)}</span>
      </div>
    </button>
  );
}
