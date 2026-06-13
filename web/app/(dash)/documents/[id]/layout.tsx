"use client";
import { use } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import { PageRail } from "@/components/PageRail";
import { Skeleton } from "@/components/ui/Skeleton";
import { useDocument } from "@/hooks/useDocument";

export default function DocumentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const q = useDocument(id);

  return (
    <Box sx={{ display: "flex", gap: 2 }}>
      {q.isLoading ? (
        <Stack spacing={1} sx={{ width: 160, flexShrink: 0, display: { xs: "none", sm: "flex" } }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </Stack>
      ) : q.data ? (
        <PageRail documentId={id} pages={q.data.pages} />
      ) : null}
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>{children}</Box>
    </Box>
  );
}
