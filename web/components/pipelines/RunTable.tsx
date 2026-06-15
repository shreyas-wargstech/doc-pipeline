import { memo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import type { RunItem } from "@/lib/types";

const STAGES = ["ingest", "ocr", "structure", "match", "persist", "index"];

export const VIRTUALIZE_THRESHOLD = 30;

function statusTone(s: RunItem["status"]): "ok" | "warn" | "danger" | "info" | "muted" {
  switch (s) {
    case "done": return "ok";
    case "failed": return "danger";
    case "running": return "info";
    default: return "muted";
  }
}

function DocumentCell({ item }: { item: RunItem }) {
  return item.document_id
    ? (
      <Link href={`/documents/${item.document_id}`} className="font-mono text-primary hover:underline">
        {item.document_id.slice(0, 12)}…
      </Link>
    )
    : <>—</>;
}

function StageCell({ item }: { item: RunItem }) {
  return (
    <>
      {item.status === "running" && item.stage
        ? `${STAGES.indexOf(item.stage) + 1}/${STAGES.length} ${item.stage}`
        : "—"}
    </>
  );
}

function ResultCell({ item }: { item: RunItem }) {
  return item.status === "failed" && item.error
    ? <span title={item.error}><Badge tone="danger">failed</Badge></span>
    : <Badge tone={statusTone(item.status)}>{item.status}</Badge>;
}

const RUN_TABLE_HEADERS = ["File", "Document", "Stage", "Result"];

const VirtualRow = memo(
  function VirtualRow({ item, start, size }: { item: RunItem; start: number; size: number }) {
    return (
      <div
        className="absolute left-0 top-0 grid w-full grid-cols-[2fr_2fr_2fr_1fr] border-b last:border-0 transition-colors duration-150 hover:bg-muted/40"
        style={{ height: size, transform: `translateY(${start}px)` }}
      >
        <div className="truncate px-3 py-2 align-middle">{item.filename}</div>
        <div className="truncate px-3 py-2 align-middle"><DocumentCell item={item} /></div>
        <div className="truncate px-3 py-2 align-middle"><StageCell item={item} /></div>
        <div className="truncate px-3 py-2 align-middle"><ResultCell item={item} /></div>
      </div>
    );
  },
  (prev, next) =>
    prev.item.filename === next.item.filename &&
    prev.item.status === next.item.status &&
    prev.item.document_id === next.item.document_id &&
    prev.item.stage === next.item.stage &&
    prev.item.error === next.item.error &&
    prev.start === next.start &&
    prev.size === next.size,
);

function VirtualizedRunTable({ items }: { items: RunItem[] }) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 41,
    overscan: 8,
  });

  return (
    <div className="overflow-x-auto rounded-lg border">
      <div className="grid grid-cols-[2fr_2fr_2fr_1fr] border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-fg">
        {RUN_TABLE_HEADERS.map((header) => (
          <div key={header} className="px-3 py-2 font-medium">{header}</div>
        ))}
      </div>
      <div ref={parentRef} style={{ height: 480, overflow: "auto" }}>
        <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const item = items[virtualRow.index];
            return (
              <VirtualRow
                key={item.filename}
                item={item}
                start={virtualRow.start}
                size={virtualRow.size}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function RunTable({ items }: { items: RunItem[] }) {
  if (items.length > VIRTUALIZE_THRESHOLD) {
    return <VirtualizedRunTable items={items} />;
  }

  return (
    <Table<RunItem>
      rows={items}
      rowKey={(it) => it.filename}
      empty="No items yet."
      columns={[
        { key: "filename", header: "File" },
        { key: "document_id", header: "Document", render: (it) => <DocumentCell item={it} /> },
        { key: "stage", header: "Stage", render: (it) => <StageCell item={it} /> },
        { key: "status", header: "Result", render: (it) => <ResultCell item={it} /> },
      ]}
    />
  );
}
