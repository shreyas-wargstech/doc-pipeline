"use client";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type { DocFilters } from "@/hooks/useDocuments";

const STATUSES = ["received", "processing", "processed", "failed", "manual_review"];
const CATEGORIES = ["practitioner", "letter", "receipt", "record", "other"];
const MATCHES = ["matched", "unmatched", "not_applicable", "manual_review"];

export function Filters({ value, onChange }: { value: DocFilters; onChange: (f: DocFilters) => void }) {
  const set = (patch: Partial<DocFilters>) => onChange({ ...value, ...patch, offset: 0 });
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label htmlFor="filter-category" className="flex flex-col gap-1 text-xs text-muted-fg">Category
        <Select id="filter-category" value={value.category ?? ""} onChange={(e) => set({ category: e.target.value || undefined })}>
          <option value="">All</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      </label>
      <label htmlFor="filter-status" className="flex flex-col gap-1 text-xs text-muted-fg">Status
        <Select id="filter-status" value={value.status ?? ""} onChange={(e) => set({ status: e.target.value || undefined })}>
          <option value="">All</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
      </label>
      <label htmlFor="filter-match" className="flex flex-col gap-1 text-xs text-muted-fg">Match
        <Select id="filter-match" value={value.match_status ?? ""} onChange={(e) => set({ match_status: e.target.value || undefined })}>
          <option value="">All</option>
          {MATCHES.map((m) => <option key={m} value={m}>{m}</option>)}
        </Select>
      </label>
      <label className="flex flex-1 flex-col gap-1 text-xs text-muted-fg">Search
        <span className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-fg" />
          <Input className="pl-9" placeholder="reg-no / filename" value={value.search ?? ""} onChange={(e) => set({ search: e.target.value || undefined })} />
        </span>
      </label>
    </div>
  );
}
