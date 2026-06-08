export function Badge({ tone = "muted", children }: { tone?: "ok" | "warn" | "danger" | "info" | "muted"; children: React.ReactNode }) {
  const map: Record<string, string> = {
    ok: "bg-ok/15 text-ok ring-ok/30",
    warn: "bg-warn/15 text-warn ring-warn/30",
    danger: "bg-danger/15 text-danger ring-danger/30",
    info: "bg-info/15 text-info ring-info/30",
    muted: "bg-muted text-muted-fg ring-border",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${map[tone]}`}>
      {children}
    </span>
  );
}
