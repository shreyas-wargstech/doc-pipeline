"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { CheckCircle2, AlertTriangle, XCircle, Info, Minus, Circle } from "lucide-react";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary: "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive: "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface ShadcnBadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function ShadcnBadge({ className, variant, ...props }: ShadcnBadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export type Tone = "primary" | "secondary" | "success" | "warn" | "danger" | "info" | "muted" | "ok";

const toneMap: Record<Tone, string> = {
  primary: "bg-primary-tint text-primary border-primary/20 rounded-pill",
  secondary: "bg-secondary-tint text-secondary border-secondary/20 rounded-pill",
  success: "bg-success-bg text-success border-success/20 rounded-pill",
  ok: "bg-ok-bg text-ok border-ok/20 rounded-pill",
  warn: "bg-warn-bg text-warn border-warn/20 rounded-pill",
  danger: "bg-danger-bg text-danger border-danger/20 rounded-pill",
  info: "bg-info-bg text-info border-info/20 rounded-pill",
  muted: "bg-surface-alt text-muted-fg border-border rounded-pill",
};

const toneIcon: Record<Tone, React.ReactNode> = {
  primary: <Circle className="mr-1 h-3 w-3" aria-hidden="true" />,
  secondary: <Circle className="mr-1 h-3 w-3" aria-hidden="true" />,
  success: <CheckCircle2 className="mr-1 h-3 w-3" aria-hidden="true" />,
  ok: <CheckCircle2 className="mr-1 h-3 w-3" aria-hidden="true" />,
  warn: <AlertTriangle className="mr-1 h-3 w-3" aria-hidden="true" />,
  danger: <XCircle className="mr-1 h-3 w-3" aria-hidden="true" />,
  info: <Info className="mr-1 h-3 w-3" aria-hidden="true" />,
  muted: <Minus className="mr-1 h-3 w-3" aria-hidden="true" />,
};

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  tone?: Tone;
}

export function Badge({ tone = "muted", className, children, ...props }: BadgeProps) {
  return (
    <ShadcnBadge className={cn(toneMap[tone], className)} {...props}>
      {toneIcon[tone]}
      {children}
    </ShadcnBadge>
  );
}
