import { render, screen } from "@testing-library/react";
import { describe, expect, it, beforeAll } from "vitest";
import { RunTable, VIRTUALIZE_THRESHOLD } from "../RunTable";
import type { RunItem } from "@/lib/types";

function makeItem(i: number): RunItem {
  return {
    filename: `file-${i}.pdf`,
    status: i % 7 === 0 ? "failed" : i % 5 === 0 ? "running" : "done",
    document_id: i % 7 === 0 ? null : `doc-${i.toString().padStart(12, "0")}`,
    stage: i % 5 === 0 ? "ocr" : null,
    error: i % 7 === 0 ? "boom" : null,
  };
}

beforeAll(() => {
  // jsdom doesn't implement layout; @tanstack/react-virtual needs a non-zero
  // viewport height to compute the visible range.
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    value: 480,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: 480,
  });
});

describe("RunTable", () => {
  it("shows the empty state with no items", () => {
    render(<RunTable items={[]} />);
    expect(screen.getByText("No items yet.")).toBeInTheDocument();
  });

  it("renders all rows directly for small lists (<= threshold)", () => {
    const items = Array.from({ length: VIRTUALIZE_THRESHOLD }, (_, i) => makeItem(i));
    render(<RunTable items={items} />);
    // every filename should be in the DOM
    for (const it of items) {
      expect(screen.getByText(it.filename)).toBeInTheDocument();
    }
  });

  it("virtualizes large lists, rendering far fewer rows than items", () => {
    const total = 200;
    const items = Array.from({ length: total }, (_, i) => makeItem(i));
    render(<RunTable items={items} />);

    // first item should be rendered (it's at the top of the scroll area)
    expect(screen.getByText("file-0.pdf")).toBeInTheDocument();

    // not all 200 filenames should be mounted at once
    const renderedFilenames = items.filter((it) =>
      screen.queryByText(it.filename) !== null
    );
    expect(renderedFilenames.length).toBeLessThan(total);
    expect(renderedFilenames.length).toBeGreaterThan(0);
  });

  it("renders failed status with the error tooltip in the virtualized path", () => {
    const total = 50;
    const items = Array.from({ length: total }, (_, i) => makeItem(i));
    render(<RunTable items={items} />);
    const failedBadges = screen.getAllByText("failed");
    expect(failedBadges.some((el) => el.closest("[title='boom']") !== null)).toBe(true);
  });
});
