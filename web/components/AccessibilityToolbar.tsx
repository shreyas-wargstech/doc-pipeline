"use client";

import { Contrast, Type, Monitor, Sun, Moon } from "lucide-react";
import { Button } from "@/components/ui/Button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAccessibility } from "@/lib/accessibility";
import { useTheme } from "@/lib/theme";

export function AccessibilityToolbar() {
  const { highContrast, largeText, toggleHighContrast, toggleLargeText } =
    useAccessibility();
  const { theme, cycleTheme } = useTheme();
  const ThemeIcon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;

  return (
    <TooltipProvider>
      <div className="flex items-center gap-1" role="group" aria-label="Accessibility controls">
        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Theme: ${theme}`}
              onClick={cycleTheme}
              className="text-muted-fg hover:text-foreground hover:bg-surface-hover"
            >
              <ThemeIcon className="h-4 w-4" aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Theme: {theme}</TooltipContent>
        </Tooltip>

        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-pressed={highContrast}
              aria-label="High contrast mode"
              onClick={toggleHighContrast}
              className={
                highContrast
                  ? "bg-primary text-on-primary hover:bg-primary/90"
                  : "text-muted-fg hover:text-foreground hover:bg-surface-hover"
              }
            >
              <Contrast className="h-4 w-4" aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>High contrast</TooltipContent>
        </Tooltip>

        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-pressed={largeText}
              aria-label="Large text mode"
              onClick={toggleLargeText}
              className={
                largeText
                  ? "bg-primary text-on-primary hover:bg-primary/90"
                  : "text-muted-fg hover:text-foreground hover:bg-surface-hover"
              }
            >
              <Type className="h-4 w-4" aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Large text</TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
}
