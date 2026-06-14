import { forwardRef } from "react";
export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className = "", ...props }, ref) {
    return (
      <input
        ref={ref}
        className={`min-h-[44px] w-full rounded-[10px] border border-border-strong bg-surface px-3 text-sm text-foreground placeholder:text-tertiary-fg transition-shadow focus-visible:outline-none focus-visible:border-primary focus-visible:ring-4 focus-visible:ring-primary/15 ${className}`}
        {...props}
      />
    );
  },
);
