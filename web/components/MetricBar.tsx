export function MetricBars({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-fg">No data yet.</p>
      ) : entries.map(([k, n]) => (
        <div key={k} className="flex items-center gap-3">
          <span className="w-32 shrink-0 truncate text-xs text-muted-fg">{k}</span>
          <div className="h-4 flex-1 overflow-hidden rounded bg-muted">
            <div className="h-full rounded bg-secondary transition-[width] duration-300" style={{ width: `${(n / max) * 100}%` }} />
          </div>
          <span className="tnum w-10 text-right text-xs text-foreground">{n}</span>
        </div>
      ))}
    </div>
  );
}
