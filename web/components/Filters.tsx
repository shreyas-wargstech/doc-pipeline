"use client";
import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type { DocFilters } from "@/hooks/useDocuments";
import type { Category, DocStatus, MatchStatus } from "@/lib/types";

const STATUSES = ["received", "processing", "processed", "failed", "manual_review"] as const;
const CATEGORIES = ["practitioner", "letter", "receipt", "record", "other"] as const;
const MATCHES = ["matched", "unmatched", "not_applicable", "manual_review"] as const;

export function Filters({ value, onChange }: { value: DocFilters; onChange: (f: DocFilters) => void }) {
  const set = (patch: Partial<DocFilters>) => onChange({ ...value, ...patch, offset: 0 });

  const [searchDraft, setSearchDraft] = useState(value.search ?? "");
  useEffect(() => { setSearchDraft(value.search ?? ""); }, [value.search]);
  useEffect(() => {
    const id = setTimeout(() => {
      if ((value.search ?? "") !== searchDraft) {
        onChange({ ...value, search: searchDraft || undefined, offset: 0 });
      }
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1">
        <label htmlFor="filter-category" className="text-xs font-medium text-muted-foreground">Category</label>
        <Select
          id="filter-category"
          value={value.category ?? ""}
          onChange={(e) => set({ category: (e.target.value || undefined) as Category | undefined })}
          className="min-w-[140px]"
        >
          <option value="">All</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="filter-status" className="text-xs font-medium text-muted-foreground">Status</label>
        <Select
          id="filter-status"
          value={value.status ?? ""}
          onChange={(e) => set({ status: (e.target.value || undefined) as DocStatus | undefined })}
          className="min-w-[140px]"
        >
          <option value="">All</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="filter-match" className="text-xs font-medium text-muted-foreground">Match</label>
        <Select
          id="filter-match"
          value={value.match_status ?? ""}
          onChange={(e) => set({ match_status: (e.target.value || undefined) as NonNullable<MatchStatus> | undefined })}
          className="min-w-[140px]"
        >
          <option value="">All</option>
          {MATCHES.map((m) => <option key={m} value={m}>{m}</option>)}
        </Select>
      </div>

      <div className="relative flex-grow min-w-[200px]">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          id="filter-search"
          placeholder="reg-no / filename"
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          className="pl-9"
        />
      </div>
    </div>
  );
}
