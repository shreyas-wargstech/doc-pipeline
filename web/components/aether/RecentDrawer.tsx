"use client";
import { Clock, ArrowUpRight, Trash2 } from "lucide-react";
import { Drawer } from "@/components/ui/Drawer";

export function RecentDrawer({
  open, onClose, recent, onPick, onClear,
}: {
  open: boolean;
  onClose: () => void;
  recent: string[];
  onPick: (query: string) => void;
  onClear: () => void;
}) {
  return (
    <Drawer open={open} onClose={onClose} title="Recent">
      {recent.length === 0 ? (
        <p className="text-sm text-muted-fg">Nothing asked yet. Your last few questions will land here.</p>
      ) : (
        <div className="flex flex-col gap-0.5">
          {recent.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => { onPick(r); onClose(); }}
              className="group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors duration-150 hover:bg-surface-hover"
            >
              <Clock className="h-3.5 w-3.5 shrink-0 text-muted-fg" />
              <span className="flex-1 truncate text-[13px]">{r}</span>
              <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-muted-fg opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
            </button>
          ))}
          <button
            type="button"
            onClick={onClear}
            className="mt-3 flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-[11px] text-muted-fg transition-colors duration-150 hover:text-danger"
          >
            <Trash2 className="h-3 w-3" /> Clear history
          </button>
        </div>
      )}
    </Drawer>
  );
}
