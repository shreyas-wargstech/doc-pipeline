import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AuditActivity, bucketByDay } from "@/components/AuditActivity";
import type { AuditRow } from "@/lib/types";

function row(ts: string, result: "ok" | "error" = "ok"): AuditRow {
  return { id: Math.random(), ts, username: "u", action: "ingest", document_id: null, params: {}, result, detail: null };
}

describe("bucketByDay", () => {
  it("counts rows per calendar day and returns `days` buckets ending today", () => {
    const today = new Date();
    const iso = (d: Date) => d.toISOString();
    const dayAgo = new Date(today.getTime() - 24 * 3600 * 1000);
    const buckets = bucketByDay([row(iso(today)), row(iso(today)), row(iso(dayAgo))], 7);
    expect(buckets).toHaveLength(7);
    expect(buckets[buckets.length - 1].count).toBe(2); // today
    expect(buckets[buckets.length - 2].count).toBe(1); // yesterday
  });

  it("ignores rows older than the window", () => {
    const old = new Date(Date.now() - 100 * 24 * 3600 * 1000).toISOString();
    const buckets = bucketByDay([row(old)], 7);
    expect(buckets.reduce((a, b) => a + b.count, 0)).toBe(0);
  });
});

describe("AuditActivity", () => {
  it("renders an empty state when there are no rows", () => {
    render(<AuditActivity rows={[]} />);
    expect(screen.getByText(/no .*activity/i)).toBeInTheDocument();
  });

  it("renders a heading when rows exist", () => {
    render(<AuditActivity rows={[row(new Date().toISOString())]} />);
    expect(screen.getByText(/activity/i)).toBeInTheDocument();
  });
});
