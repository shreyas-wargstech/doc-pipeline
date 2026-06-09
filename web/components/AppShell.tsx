"use client";
import { FileText, ListChecks, LogOut, BarChart3, FlaskConical } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { Button } from "@/components/ui/Button";
import { useLogout } from "@/hooks/useAuth";

const nav = [
  { href: "/", label: "Documents", icon: FileText },
  { href: "/metrics", label: "Metrics", icon: BarChart3 },
  { href: "/audit", label: "Audit", icon: ListChecks },
  { href: "/eval", label: "Eval", icon: FlaskConical },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const logout = useLogout();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-40 flex items-center gap-1 border-b bg-card/90 px-4 py-2 backdrop-blur">
        <span className="mr-4 font-mono text-sm font-bold text-primary">doc-pipeline</span>
        <nav className="flex items-center gap-1">
          {nav.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={`inline-flex min-h-[44px] items-center gap-2 rounded-md px-3 text-sm transition-colors duration-150 hover:bg-muted ${isActive(href) ? "bg-muted font-medium text-primary" : "text-foreground"}`}>
              <Icon className="h-4 w-4" />{label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <Button variant="ghost" onClick={() => logout.mutate()} aria-label="Sign out"><LogOut className="h-4 w-4" /></Button>
        </div>
      </header>
      <main className="mx-auto max-w-7xl p-4">{children}</main>
    </div>
  );
}
