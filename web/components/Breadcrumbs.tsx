"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";

const SECTION_LABELS: Record<string, string> = {
  documents: "Documents",
  eval: "Evaluation",
  audit: "Audit",
  metrics: "Metrics",
  pipelines: "Pipelines",
  retrieval: "Retrieval",
  observability: "Observability",
  admin: "Admin",
};

interface Crumb {
  label: string;
  href: string;
}

function buildCrumbs(pathname: string): Crumb[] {
  const segments = pathname.split("/").filter(Boolean);

  if (segments.length === 0) {
    return [{ label: "Documents", href: "/" }];
  }

  if (segments[0] === "documents" && segments.length >= 2) {
    const docId = segments[1];
    const crumbs: Crumb[] = [
      { label: "Documents", href: "/" },
      { label: `${docId.slice(0, 8)}…`, href: `/documents/${docId}` },
    ];
    if (segments.length >= 4 && segments[2] === "pages") {
      crumbs.push({ label: `Page ${segments[3]}`, href: pathname });
    }
    return crumbs;
  }

  const label = SECTION_LABELS[segments[0]] ?? segments[0];
  return [{ label, href: `/${segments[0]}` }];
}

export function Breadcrumbs() {
  const pathname = usePathname();
  const crumbs = buildCrumbs(pathname);

  return (
    <nav aria-label="breadcrumb">
      <ol className="flex items-center gap-1">
        {crumbs.map((crumb, i) => (
          <li key={crumb.href} className="flex items-center gap-1">
            {i > 0 && (
              <ChevronRight className="h-3.5 w-3.5 text-muted-fg shrink-0" aria-hidden="true" />
            )}
            {i === crumbs.length - 1 ? (
              <span className="text-sm text-foreground font-medium truncate">
                {crumb.label}
              </span>
            ) : (
              <Link
                href={crumb.href}
                className="text-sm text-muted-fg font-medium hover:text-foreground transition-colors"
              >
                {crumb.label}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
