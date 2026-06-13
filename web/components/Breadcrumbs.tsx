"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import MuiBreadcrumbs from "@mui/material/Breadcrumbs";
import MuiLink from "@mui/material/Link";
import Typography from "@mui/material/Typography";

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
    <MuiBreadcrumbs aria-label="breadcrumb">
      {crumbs.map((crumb, i) =>
        i === crumbs.length - 1 ? (
          <Typography key={crumb.href} variant="body2" color="text.primary">
            {crumb.label}
          </Typography>
        ) : (
          <MuiLink key={crumb.href} component={Link} href={crumb.href} underline="hover" color="inherit" variant="body2">
            {crumb.label}
          </MuiLink>
        ),
      )}
    </MuiBreadcrumbs>
  );
}
