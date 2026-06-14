export function ProgressBar({ done, total }: { done: number; total: number }) {
  const clampedDone = Math.min(done, total);
  const pct = total > 0 ? Math.round((clampedDone / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div
        role="progressbar"
        aria-label={`OCR ${clampedDone} of ${total} pages`}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={clampedDone}
        className="h-2 w-24 overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full bg-muted transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
      <span className="tnum text-xs text-muted-fg">{done}/{total}</span>
    </div>
  );
}
