import type { AuditRow } from "@/lib/types";

export interface DayBucket {
  /** Local calendar day key, e.g. "2026-06-15". */
  day: string;
  /** Short label for the axis, e.g. "Jun 15". */
  label: string;
  count: number;
}

function dayKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/**
 * Bucket audit rows into the last `days` calendar days (local time), oldest
 * first, ending with today. Rows outside the window are ignored. Pure — no I/O.
 */
export function bucketByDay(rows: AuditRow[], days = 14): DayBucket[] {
  const today = new Date();
  const buckets: DayBucket[] = [];
  const index = new Map<string, DayBucket>();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
    const b: DayBucket = {
      day: dayKey(d),
      label: d.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      count: 0,
    };
    buckets.push(b);
    index.set(b.day, b);
  }
  for (const r of rows) {
    const ts = new Date(r.ts);
    if (Number.isNaN(ts.getTime())) continue;
    const b = index.get(dayKey(ts));
    if (b) b.count += 1;
  }
  return buckets;
}

export function AuditActivity({ rows, days = 14 }: { rows: AuditRow[]; days?: number }) {
  const buckets = bucketByDay(rows, days);
  const total = buckets.reduce((a, b) => a + b.count, 0);
  const max = Math.max(1, ...buckets.map((b) => b.count));

  if (total === 0) {
    return (
      <div className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-foreground">Activity (last {days} days)</h2>
        <p className="text-sm text-muted-fg">No recent activity.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold text-foreground">Activity (last {days} days)</h2>
      <div className="flex items-end gap-1" style={{ height: 64 }}>
        {buckets.map((b) => (
          <div key={b.day} className="group flex flex-1 flex-col items-center justify-end gap-1" title={`${b.label}: ${b.count}`}>
            <div
              className="w-full rounded-t bg-primary/80 transition-[height] duration-300 group-hover:bg-primary"
              style={{ height: `${(b.count / max) * 48 + (b.count ? 4 : 0)}px` }}
              aria-hidden
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-muted-fg">
        <span>{buckets[0].label}</span>
        <span>{buckets[buckets.length - 1].label}</span>
      </div>
    </div>
  );
}
