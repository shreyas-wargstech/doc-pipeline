"use client";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type { Category } from "@/lib/types";

const CATEGORIES: Category[] = ["practitioner", "letter", "receipt", "record"];

export function RunForm({
  onRun, disabled,
}: {
  onRun: (args: { folder: string; category: string; force: boolean }) => void;
  disabled: boolean;
}) {
  const [folder, setFolder] = useState("");
  const [category, setCategory] = useState("practitioner");
  const [force, setForce] = useState(false);

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="run-folder" className="text-xs font-medium text-muted-fg">Server folder path</label>
        <Input
          id="run-folder"
          value={folder}
          onChange={(e) => setFolder(e.target.value)}
          placeholder="/data/incoming"
        />
      </div>
      <div className="flex flex-col gap-1 max-w-60">
        <label htmlFor="run-category" className="text-xs font-medium text-muted-fg">Category</label>
        <Select id="run-category" value={category} onChange={(e) => setCategory(e.target.value)}>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      </div>
      <label className="flex items-center gap-2 text-sm text-foreground">
        <input
          type="checkbox"
          checked={force}
          onChange={(e) => setForce(e.target.checked)}
          className="h-4 w-4 rounded border-border-strong"
        />
        Force reprocess already-processed documents
      </label>
      <Button
        disabled={disabled || !folder.trim()}
        onClick={() => onRun({ folder: folder.trim(), category, force })}
        className="self-start"
      >
        Run folder
      </Button>
    </Card>
  );
}
