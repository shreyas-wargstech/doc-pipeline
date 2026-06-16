"use client";

import { Contrast, Type } from "lucide-react";
import { useAccessibility } from "@/lib/accessibility";

export function AccessibilityToolbar() {
  const { highContrast, largeText, toggleHighContrast, toggleLargeText } = useAccessibility();

  return (
    <div className="flex items-center gap-2" role="group" aria-label="Accessibility controls">
      <button
        type="button"
        aria-pressed={highContrast}
        aria-label="High contrast mode"
        title="High contrast"
        onClick={toggleHighContrast}
        className={`inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-semibold transition-colors ${
          highContrast
            ? "bg-primary text-on-primary"
            : "bg-surface-alt text-muted-fg hover:bg-primary-tint hover:text-primary"
        }`}
      >
        <Contrast className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="sr-only">High contrast</span>
        <span aria-hidden="true">HC</span>
      </button>
      <button
        type="button"
        aria-pressed={largeText}
        aria-label="Large text mode"
        title="Large text"
        onClick={toggleLargeText}
        className={`inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-semibold transition-colors ${
          largeText
            ? "bg-primary text-on-primary"
            : "bg-surface-alt text-muted-fg hover:bg-primary-tint hover:text-primary"
        }`}
      >
        <Type className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="sr-only">Large text</span>
        <span aria-hidden="true">A+</span>
      </button>
    </div>
  );
}
