// web/components/admin/UsersTable.tsx
"use client";
import { useState } from "react";
import { Lock, LockOpen, Key, Trash2 } from "lucide-react";
import { Table } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { useAdminUsers, useDeleteUser, useSetUserActive, useUpdateUserRole } from "@/hooks/useAdminUsers";
import { useMe } from "@/hooks/useAuth";
import { fmtDateTime } from "@/lib/format";
import type { AdminUser, UserRole } from "@/lib/types";
import { ResetPasswordDialog } from "./ResetPasswordDialog";

const ROLES: UserRole[] = ["administrator", "reviewer", "operator", "viewer"];

export function UsersTable() {
  const { data, isLoading } = useAdminUsers();
  const { data: me } = useMe();
  const updateRole = useUpdateUserRole();
  const setActive = useSetUserActive();
  const deleteUser = useDeleteUser();
  const [resetTarget, setResetTarget] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    );
  }

  const users: AdminUser[] = data?.users ?? [];
  const isSelf = (u: AdminUser) => u.username === me?.user;

  return (
    <TooltipProvider>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-fg">
              <th className="px-3 py-2 font-medium">Username</th>
              <th className="px-3 py-2 font-medium">Role</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Created</th>
              <th className="px-3 py-2 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.username} className="border-b last:border-0 transition-colors duration-150 hover:bg-muted/40">
                <td className="px-3 py-2 align-middle font-mono text-xs">
                  {u.username}
                  {isSelf(u) && (
                    <span className="ml-1 text-xs text-muted-fg">(you)</span>
                  )}
                </td>
                <td className="px-3 py-2 align-middle">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span>
                        <Select
                          disabled={isSelf(u)}
                          value={u.role}
                          onChange={(e) =>
                            updateRole.mutate({ username: u.username, role: e.target.value as UserRole })
                          }
                          className="text-xs"
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </Select>
                      </span>
                    </TooltipTrigger>
                    {isSelf(u) && (
                      <TooltipContent>Cannot change your own role</TooltipContent>
                    )}
                  </Tooltip>
                </td>
                <td className="px-3 py-2 align-middle">
                  <Badge tone={u.is_active ? "ok" : "muted"}>{u.is_active ? "active" : "inactive"}</Badge>
                </td>
                <td className="px-3 py-2 align-middle text-xs text-muted-fg">
                  {fmtDateTime(u.created_at)}
                </td>
                <td className="px-3 py-2 align-middle text-right">
                  <div className="flex items-center justify-end gap-1">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="icon" onClick={() => setResetTarget(u.username)}>
                          <Key className="h-4 w-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Reset password</TooltipContent>
                    </Tooltip>

                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span>
                          <Button
                            variant="ghost"
                            size="icon"
                            disabled={isSelf(u)}
                            onClick={() => setActive.mutate({ username: u.username, is_active: !u.is_active })}
                          >
                            {u.is_active ? <Lock className="h-4 w-4" /> : <LockOpen className="h-4 w-4" />}
                          </Button>
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>
                        {isSelf(u) ? "Cannot deactivate yourself" : u.is_active ? "Deactivate" : "Reactivate"}
                      </TooltipContent>
                    </Tooltip>

                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span>
                          <Button
                            variant="ghost"
                            size="icon"
                            disabled={isSelf(u)}
                            onClick={() => {
                              if (window.confirm(`Delete user "${u.username}"? This cannot be undone.`)) {
                                deleteUser.mutate(u.username);
                              }
                            }}
                          >
                            <Trash2 className="h-4 w-4 text-danger" />
                          </Button>
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>
                        {isSelf(u) ? "Cannot delete yourself" : "Delete"}
                      </TooltipContent>
                    </Tooltip>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {resetTarget && (
        <ResetPasswordDialog
          username={resetTarget}
          onClose={() => setResetTarget(null)}
        />
      )}
    </TooltipProvider>
  );
}
