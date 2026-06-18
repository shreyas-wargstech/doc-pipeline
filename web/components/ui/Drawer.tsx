"use client";
import { type ReactNode } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "./sheet";
import { cn } from "@/lib/utils";

export function Drawer({
  open,
  title,
  onClose,
  children,
  className,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Sheet open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
      <SheetContent side="right" className={cn("w-full max-w-md p-0", className)}>
        <div className="flex h-full flex-col">
          <SheetHeader className="sticky top-0 z-10 space-y-0 border-b bg-card px-4 py-3 pr-12 text-left sm:text-left">
            <SheetTitle className="text-base font-semibold text-foreground">{title}</SheetTitle>
          </SheetHeader>
          <div className="flex flex-col gap-4 overflow-y-auto p-4">{children}</div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
