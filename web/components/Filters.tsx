"use client";
import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import InputAdornment from "@mui/material/InputAdornment";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import SearchIcon from "@mui/icons-material/Search";
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
      if ((value.search ?? "") !== searchDraft) {
        onChange({ ...value, search: searchDraft || undefined, offset: 0 });
      }
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 2 }}>
      <FormControl size="small" sx={{ minWidth: 140 }}>
        <InputLabel id="filter-category-label" htmlFor="filter-category">Category</InputLabel>
        <Select
          native
          id="filter-category"
          labelId="filter-category-label"
          label="Category"
          value={value.category ?? ""}
          onChange={(e) => set({ category: (e.target.value || undefined) as Category | undefined })}
        >
          <option value="">All</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ minWidth: 140 }}>
        <InputLabel id="filter-status-label" htmlFor="filter-status">Status</InputLabel>
        <Select
          native
          id="filter-status"
          labelId="filter-status-label"
          label="Status"
          value={value.status ?? ""}
          onChange={(e) => set({ status: (e.target.value || undefined) as DocStatus | undefined })}
        >
          <option value="">All</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ minWidth: 140 }}>
        <InputLabel id="filter-match-label" htmlFor="filter-match">Match</InputLabel>
        <Select
          native
          id="filter-match"
          labelId="filter-match-label"
          label="Match"
          value={value.match_status ?? ""}
          onChange={(e) => set({ match_status: (e.target.value || undefined) as NonNullable<MatchStatus> | undefined })}
        >
          <option value="">All</option>
          {MATCHES.map((m) => <option key={m} value={m}>{m}</option>)}
        </Select>
      </FormControl>

      <TextField
        size="small"
        label="Search"
        placeholder="reg-no / filename"
        value={searchDraft}
        onChange={(e) => setSearchDraft(e.target.value)}
        sx={{ flexGrow: 1, minWidth: 200 }}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          },
        }}
      />
    </Box>
  );
}
