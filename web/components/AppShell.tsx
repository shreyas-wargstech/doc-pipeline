"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import {
  Menu,
  ChevronLeft,
  ChevronRight,
  LogOut,
  UserCircle,
  FileText,
  CheckSquare,
  GitBranch,
  Search,
  Activity,
  Shield,
  Bookmark,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

import { Breadcrumbs } from "@/components/Breadcrumbs";
import { AccessibilityToolbar } from "@/components/AccessibilityToolbar";
import { useActionBarContent } from "@/app/action-bar";
import { useLogout, useRole } from "@/hooks/useAuth";
import { useCollapsible } from "@/hooks/useCollapsible";

const DRAWER_WIDTH = 240;
const COLLAPSED_WIDTH = 64;

const NAV_ITEMS = [
  { href: "/", label: "Documents", icon: FileText },
  { href: "/bookmarks", label: "Bookmarks", icon: Bookmark },
  { href: "/eval", label: "Evaluation", icon: CheckSquare },
  { href: "/pipelines", label: "Pipelines", icon: GitBranch },
  { href: "/retrieval", label: "Retrieval", icon: Search },
  { href: "/observability", label: "Observability", icon: Activity },
  { href: "/admin", label: "Admin", icon: Shield },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const logout = useLogout();
  const actionBarContent = useActionBarContent();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { collapsed, toggle } = useCollapsible("app-sidebar", false);
  const sidebarWidth = collapsed ? COLLAPSED_WIDTH : DRAWER_WIDTH;
  const role = useRole();

  const visibleNavItems = NAV_ITEMS.filter(
    ({ href }) => href !== "/admin" || role === "administrator",
  );

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  const navList = (
    <nav className="flex flex-col gap-1 px-2 py-2" aria-label="Main">
      {visibleNavItems.map(({ href, label, icon: Icon }) => {
        const active = isActive(href);
        const linkContent = (
          <Link
            href={href}
            aria-current={active ? "page" : undefined}
            className={
              "flex items-center gap-3 rounded-lg px-3 py-2 transition-all duration-150 " +
              (active
                ? "bg-primary-tint text-primary font-medium"
                : "text-muted-fg hover:text-foreground hover:bg-surface-hover hover:translate-x-0.5")
            }
          >
            <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
            {!collapsed && (
              <span className="text-sm truncate">{label}</span>
            )}
          </Link>
        );

        return collapsed ? (
          <Tooltip key={href} delayDuration={300}>
            <TooltipTrigger asChild>
              {linkContent}
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={8}>
              {label}
            </TooltipContent>
          </Tooltip>
        ) : (
          <div key={href}>{linkContent}</div>
        );
      })}
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <TooltipProvider>
        <motion.aside
          className="hidden sm:flex flex-col border-r bg-surface-alt shrink-0 h-screen sticky top-0 z-40"
          initial={false}
          animate={{ width: sidebarWidth }}
          transition={{ duration: 0.3, ease: "easeInOut" }}
          style={{ width: sidebarWidth }}
        >
          {/* Header spacer */}
          <div className="h-14 shrink-0" />
          {/* Sidebar toggle */}
          <div className="flex justify-end px-2 py-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={toggle}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? (
                <ChevronRight className="h-4 w-4" />
              ) : (
                <ChevronLeft className="h-4 w-4" />
              )}
            </Button>
          </div>
          {navList}
          {!collapsed && (
            <div className="mt-auto p-4 font-mono text-xs text-muted-fg">
              92,431 registry rows
            </div>
          )}
        </motion.aside>
      </TooltipProvider>

      {/* Mobile drawer */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-60 p-0">
          <div className="h-14" />
          {navList}
        </SheetContent>
      </Sheet>

      {/* Main area */}
      <div className="flex flex-col flex-1">
        {/* Header */}
        <header className="sticky top-0 z-50 h-14 flex items-center gap-3 border-b bg-background/80 backdrop-blur-md px-4 shrink-0">
          <Button
            variant="ghost"
            size="icon"
            className="sm:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Toggle navigation"
          >
            <Menu className="h-5 w-5" />
          </Button>

          <div className="flex items-center gap-2 mr-4 shrink-0">
            <div
              aria-hidden
              className="w-6 h-6 rounded-lg bg-gradient-to-br from-teal-300 to-primary shadow-md"
            />
            <span className="font-display font-semibold text-lg tracking-wide">
              Docintel
            </span>
          </div>

          <div className="flex-1 min-w-0 hidden sm:block">
            <Breadcrumbs />
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <AccessibilityToolbar />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="Account menu">
                  <Avatar className="h-8 w-8">
                    <AvatarFallback>
                      <UserCircle className="h-5 w-5 text-muted-fg" />
                    </AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={4}>
                <DropdownMenuItem
                  onClick={() => logout.mutate()}
                  className="cursor-pointer"
                >
                  <LogOut className="h-4 w-4 mr-2" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {/* Action bar */}
        {actionBarContent && (
          <div className="sticky top-14 z-40 border-b bg-surface/80 backdrop-blur-sm flex items-center gap-2 px-4 py-2">
            {actionBarContent}
          </div>
        )}

        {/* Main content */}
        <main className="flex-1 min-h-[calc(100dvh-3.5rem)] p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
