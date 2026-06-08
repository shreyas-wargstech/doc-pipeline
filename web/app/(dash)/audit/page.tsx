"use client";
import { useState } from "react";
import { AuditTable } from "@/components/AuditTable";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAudit, type AuditFilters } from "@/hooks/useAudit";

export default function AuditPage() {
  const [f, setF] = useState<AuditFilters>({});
  const q = useAudit(f);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Input className="max-w-[12rem]" placeholder="username" value={f.username ?? ""} onChange={(e) => setF({ ...f, username: e.target.value || undefined })} />
        <Input className="max-w-[12rem]" placeholder="action" value={f.action ?? ""} onChange={(e) => setF({ ...f, action: e.target.value || undefined })} />
        <Input className="max-w-[20rem] font-mono" placeholder="document_id" value={f.document_id ?? ""} onChange={(e) => setF({ ...f, document_id: e.target.value || undefined })} />
      </div>
      {q.isLoading ? <Skeleton className="h-64 w-full" />
        : q.isError || !q.data ? <p className="text-sm text-danger">Failed to load audit log.</p>
        : <AuditTable rows={q.data.rows} />}
    </div>
  );
}
