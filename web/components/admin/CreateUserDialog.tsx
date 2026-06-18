"use client";
import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { ApiError } from "@/lib/api";
import { useCreateUser } from "@/hooks/useAdminUsers";
import type { UserRole } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function CreateUserDialog({ open, onClose }: Props) {
  const create = useCreateUser();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("viewer");
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setUsername("");
    setPassword("");
    setRole("viewer");
    setError(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({ username, password, role });
      reset();
      onClose();
    } catch (err: unknown) {
      const status = err instanceof ApiError ? err.status : null;
      setError(
        status === 409
          ? "Username already exists."
          : "Failed to create user. Try again.",
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Create user</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3 pt-1">
            <div className="flex flex-col gap-1">
              <label htmlFor="create-username" className="text-xs font-medium text-muted-fg">Username</label>
              <Input
                id="create-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="create-password" className="text-xs font-medium text-muted-fg">Password</label>
              <Input
                id="create-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="create-role" className="text-xs font-medium text-muted-fg">Role</label>
              <Select
                id="create-role"
                value={role}
                onChange={(e) => setRole(e.target.value as UserRole)}
              >
                <option value="administrator">administrator</option>
                <option value="reviewer">reviewer</option>
                <option value="operator">operator</option>
                <option value="viewer">viewer</option>
              </Select>
            </div>
            {error && (
              <p className="text-xs text-danger">{error}</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={handleClose} type="button">
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
