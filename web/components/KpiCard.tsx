import { Card } from "@/components/ui/Card";

export function KpiCard({ label, value, tone = "foreground" }: { label: string; value: number | string; tone?: string }) {
  return (
    <Card className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-muted-fg">{label}</span>
      <span className={`tnum text-2xl font-semibold text-${tone}`}>{value}</span>
    </Card>
  );
}
