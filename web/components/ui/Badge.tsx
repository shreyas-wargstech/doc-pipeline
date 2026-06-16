type Tone = "ok" | "warn" | "danger" | "info" | "muted";

import { Check, AlertTriangle, X, Clock, Minus } from "lucide-react";

const toneMap: Record<Tone, { className: string; icon: typeof Check }> = {
  ok: { className: "bg-ok/10 text-ok", icon: Check },
  warn: { className: "bg-warn/10 text-warn", icon: AlertTriangle },
  danger: { className: "bg-danger/10 text-danger", icon: X },
  info: { className: "bg-info/10 text-info", icon: Clock },
  muted: { className: "bg-surface-alt text-muted-fg", icon: Minus },
};

export function Badge({ tone = "muted", children }: { tone?: Tone; children: React.ReactNode }) {
  const { className, icon: Icon } = toneMap[tone];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${className}`}>
      <Icon aria-hidden="true" className="h-3 w-3" />
      {children}
    </span>
  );
}
