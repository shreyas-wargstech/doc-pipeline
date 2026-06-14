import { forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "destructive";
const styles: Record<Variant, string> = {
  primary: "bg-primary text-primary-fg shadow-sm hover:bg-primary-hover hover:-translate-y-px",
  secondary: "bg-surface-alt text-foreground border border-border-strong hover:border-primary",
  ghost: "bg-transparent text-foreground hover:bg-surface-alt",
  destructive: "bg-destructive text-white hover:opacity-90",
};

export const Button = forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }
>(function Button({ variant = "primary", loading, disabled, className = "", children, ...props }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={`inline-flex min-h-[44px] items-center justify-center gap-2 rounded-[10px] px-4 text-sm font-semibold transition-[background,transform,border-color] duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 ${styles[variant]} ${className}`}
      {...props}
    >
      {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />}
      {children}
    </button>
  );
});
