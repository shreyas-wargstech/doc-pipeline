export function Select({ className = "", children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`min-h-[44px] rounded-md border bg-card px-3 text-sm text-foreground cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${className}`}
      {...props}
    >
      {children}
    </select>
  );
}
