import { Card } from "@/components/ui/Card";

type Tone = "foreground" | "ok" | "warn" | "danger" | "info";

export function KpiCard({ label, value, tone = "foreground" }: { label: string; value: number | string; tone?: Tone }) {
  return (
    <Card className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-muted-fg">{label}</span>
      <span className={`tnum text-2xl font-semibold text-${tone}`}>{value}</span>
    </Card>
  );
}
