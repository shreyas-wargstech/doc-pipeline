export function Card({ className = "", ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={`rounded-xl border border-border bg-surface p-4 shadow-sm ${className}`} {...props} />;
}
