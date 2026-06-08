export function Card({ className = "", ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={`rounded-lg border bg-card p-4 shadow-sm ${className}`} {...props} />;
}
