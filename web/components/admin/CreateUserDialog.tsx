"use client";
import { useState } from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
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
    <Dialog open={open} onClose={handleClose} maxWidth="xs" fullWidth>
      <DialogTitle>Create user</DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
          <TextField
            label="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
            size="small"
          />
          <TextField
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            size="small"
          />
          <FormControl size="small">
            <InputLabel>Role</InputLabel>
            <Select
              value={role}
              label="Role"
              onChange={(e) => setRole(e.target.value as UserRole)}
            >
              <MenuItem value="administrator">administrator</MenuItem>
              <MenuItem value="reviewer">reviewer</MenuItem>
              <MenuItem value="operator">operator</MenuItem>
              <MenuItem value="viewer">viewer</MenuItem>
            </Select>
          </FormControl>
          {error && (
            <Typography color="error" variant="caption">
              {error}
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Create"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
