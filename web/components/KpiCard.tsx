import { Card } from "@/components/ui/Card";
import { CardContent } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

type Tone = "foreground" | "ok" | "warn" | "danger" | "info";

const TONE_CLASS: Record<Tone, string> = {
  foreground: "text-foreground",
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
  info: "text-info",
};

export function KpiCard({ label, value, tone = "foreground" }: { label: string; value: number | string; tone?: Tone }) {
  return (
    <Card className="border">
      <CardContent className="flex flex-col gap-1 p-4">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-fg">
          {label}
        </span>
        <span className={cn("tnum font-display text-2xl font-semibold", TONE_CLASS[tone])}>
          {value}
        </span>
      </CardContent>
    </Card>
  );
}
