"use client";
import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type { DocFilters } from "@/hooks/useDocuments";
import type { Category, DocStatus, MatchStatus } from "@/lib/types";

const STATUSES = ["received", "processing", "processed", "failed", "manual_review"];
const CATEGORIES = ["practitioner", "letter", "receipt", "record", "other"];
const MATCHES = ["matched", "unmatched", "not_applicable", "manual_review"];

export function Filters({ value, onChange }: { value: DocFilters; onChange: (f: DocFilters) => void }) {
  const set = (patch: Partial<DocFilters>) => onChange({ ...value, ...patch, offset: 0 });

  const [searchDraft, setSearchDraft] = useState(value.search ?? "");
  useEffect(() => { setSearchDraft(value.search ?? ""); }, [value.search]);
  useEffect(() => {
    const id = setTimeout(() => {
      // only emit if it actually differs from current parent value (avoids redundant fetch on mount/sync)
      if ((value.search ?? "") !== searchDraft) {
        onChange({ ...value, search: searchDraft || undefined, offset: 0 });
      }
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  return (
    <div className="flex flex-wrap items-end gap-2">
      <label htmlFor="filter-category" className="flex flex-col gap-1 text-xs text-muted-fg">Category
        <Select id="filter-category" value={value.category ?? ""} onChange={(e) => set({ category: (e.target.value || undefined) as Category | undefined })}>
          <option value="">All</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      </label>
      <label htmlFor="filter-status" className="flex flex-col gap-1 text-xs text-muted-fg">Status
        <Select id="filter-status" value={value.status ?? ""} onChange={(e) => set({ status: (e.target.value || undefined) as DocStatus | undefined })}>
          <option value="">All</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
      </label>
      <label htmlFor="filter-match" className="flex flex-col gap-1 text-xs text-muted-fg">Match
        <Select id="filter-match" value={value.match_status ?? ""} onChange={(e) => set({ match_status: (e.target.value || undefined) as NonNullable<MatchStatus> | undefined })}>
          <option value="">All</option>
          {MATCHES.map((m) => <option key={m} value={m}>{m}</option>)}
        </Select>
      </label>
      <label className="flex flex-1 flex-col gap-1 text-xs text-muted-fg">Search
        <span className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-fg" />
          <Input className="pl-9" placeholder="reg-no / filename" value={searchDraft} onChange={(e) => setSearchDraft(e.target.value)} />
        </span>
      </label>
    </div>
  );
}
