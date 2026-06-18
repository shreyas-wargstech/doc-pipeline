import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AuditDetailDrawer } from "@/components/AuditDetailDrawer";
import type { AuditRow } from "@/lib/types";

const sampleRow: AuditRow = {
  id: 42,
  ts: "2026-06-15T10:00:00Z",
  username: "alice",
  action: "requeue_ocr",
  document_id: "doc-abc-123",
  params: { page_nums: [2, 3] },
  result: "error",
  detail: "boom happened",
};

describe("AuditDetailDrawer", () => {
  it("renders nothing when no row is selected", () => {
    const { container } = render(<AuditDetailDrawer row={null} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the selected row's fields", () => {
    render(<AuditDetailDrawer row={sampleRow} onClose={() => {}} />);
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("requeue_ocr")).toBeInTheDocument();
    expect(screen.getByText("error")).toBeInTheDocument();
    expect(screen.getByText("boom happened")).toBeInTheDocument();
    expect(screen.getByText(/doc-abc-123/)).toBeInTheDocument();
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    render(<AuditDetailDrawer row={sampleRow} onClose={onClose} />);
    const closeBtn = screen.getByRole("button", { name: /close/i });
    closeBtn.click();
    expect(onClose).toHaveBeenCalled();
  });
});
