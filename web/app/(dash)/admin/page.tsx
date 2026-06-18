"use client";
import { useState } from "react";
import { UserPlus } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { CreateUserDialog } from "@/components/admin/CreateUserDialog";
import { UsersTable } from "@/components/admin/UsersTable";
import { useRole } from "@/hooks/useAuth";

export default function AdminPage() {
  const role = useRole();
  const [createOpen, setCreateOpen] = useState(false);

  if (role !== null && role !== "administrator") {
    return (
      <div className="mt-8 rounded-panel border border-danger bg-danger-bg p-4 text-sm text-danger">
        Access denied — administrator role required.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <PageHeader
        title="Admin"
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setCreateOpen(true)}
          >
            <UserPlus className="mr-2 h-4 w-4" />
            Invite user
          </Button>
        }
      />
      <UsersTable />
      <CreateUserDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
