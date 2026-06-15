// web/components/admin/UsersTable.tsx
"use client";
import { useState } from "react";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";
import LockOpenIcon from "@mui/icons-material/LockOpenOutlined";
import LockIcon from "@mui/icons-material/LockOutlined";
import KeyIcon from "@mui/icons-material/Key";
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

  if (isLoading) return <CircularProgress size={24} />;

  const users: AdminUser[] = data?.users ?? [];

  const isSelf = (u: AdminUser) => u.username === me?.user;

  return (
    <>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Username</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Created</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {users.map((u) => (
              <TableRow key={u.username} hover>
                <TableCell sx={{ fontFamily: "var(--font-mono)", fontSize: 13 }}>
                  {u.username}
                  {isSelf(u) && (
                    <Typography component="span" variant="caption" sx={{ ml: 1, color: "text.secondary" }}>
                      (you)
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <Tooltip title={isSelf(u) ? "Cannot change your own role" : ""}>
                    <span>
                      <FormControl size="small" disabled={isSelf(u)}>
                        <Select
                          value={u.role}
                          onChange={(e) =>
                            updateRole.mutate({ username: u.username, role: e.target.value as UserRole })
                          }
                          sx={{ fontSize: 13 }}
                        >
                          {ROLES.map((r) => (
                            <MenuItem key={r} value={r} sx={{ fontSize: 13 }}>{r}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </span>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  <Chip
                    label={u.is_active ? "active" : "inactive"}
                    color={u.is_active ? "success" : "default"}
                    size="small"
                    variant="outlined"
                  />
                </TableCell>
                <TableCell sx={{ color: "text.secondary", fontSize: 12 }}>
                  {fmtDateTime(u.created_at)}
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Reset password">
                    <IconButton size="small" onClick={() => setResetTarget(u.username)}>
                      <KeyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={isSelf(u) ? "Cannot deactivate yourself" : u.is_active ? "Deactivate" : "Reactivate"}>
                    <span>
                      <IconButton
                        size="small"
                        disabled={isSelf(u)}
                        onClick={() => setActive.mutate({ username: u.username, is_active: !u.is_active })}
                      >
                        {u.is_active ? <LockIcon fontSize="small" /> : <LockOpenIcon fontSize="small" />}
                      </IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title={isSelf(u) ? "Cannot delete yourself" : "Delete"}>
                    <span>
                      <IconButton
                        size="small"
                        color="error"
                        disabled={isSelf(u)}
                        onClick={() => {
                          if (window.confirm(`Delete user "${u.username}"? This cannot be undone.`)) {
                            deleteUser.mutate(u.username);
                          }
                        }}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {resetTarget && (
        <ResetPasswordDialog
          username={resetTarget}
          onClose={() => setResetTarget(null)}
        />
      )}
    </>
  );
}
