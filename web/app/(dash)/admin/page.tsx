import { ComingSoon } from "@/components/ComingSoon";

export default function AdminPage() {
  return (
    <ComingSoon
      title="Admin"
      items={[
        "Users",
        "Roles and permissions matrix",
        "Workspace and document access groups",
        "Audit log",
        "System configuration",
      ]}
    />
  );
}
