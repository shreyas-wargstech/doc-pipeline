"use client";
import { AppShell } from "@/components/AppShell";
import { useDocumentStream } from "@/hooks/useDocumentStream";

export default function DashLayout({ children }: { children: React.ReactNode }) {
  useDocumentStream();
  return <AppShell>{children}</AppShell>;
}
