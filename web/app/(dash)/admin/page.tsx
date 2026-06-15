"use client";
import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import PersonAddIcon from "@mui/icons-material/PersonAddOutlined";
import { PageHeader } from "@/components/ui/PageHeader";
import { CreateUserDialog } from "@/components/admin/CreateUserDialog";
import { UsersTable } from "@/components/admin/UsersTable";
import { useRole } from "@/hooks/useAuth";

export default function AdminPage() {
  const role = useRole();
  const [createOpen, setCreateOpen] = useState(false);

  if (role !== null && role !== "administrator") {
    return (
      <Box sx={{ mt: 4 }}>
        <Alert severity="error">Access denied — administrator role required.</Alert>
      </Box>
    );
  }

  return (
    <Box>
      <PageHeader
        title="Admin"
        actions={
          <Button
            startIcon={<PersonAddIcon />}
            variant="outlined"
            size="small"
            onClick={() => setCreateOpen(true)}
          >
            Invite user
          </Button>
        }
      />
      <UsersTable />
      <CreateUserDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </Box>
  );
}
