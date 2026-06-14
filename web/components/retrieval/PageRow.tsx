import type { SearchPageHit } from "@/lib/types";

const IDENTITY_TYPES = new Set(["app_cover", "application_form", "form", "cover"]);

function chipClass(pageType: string | null): string {
  if (pageType && IDENTITY_TYPES.has(pageType)) return "bg-primary-tint text-primary";
  return "bg-surface-alt text-muted-fg";
}

export function PageRow({ hit }: { hit: SearchPageHit }) {
  return (
    <div className="flex gap-3 rounded-[10px] border border-border bg-background p-2.5">
      <div className="relative flex h-[72px] w-14 shrink-0 items-center justify-center rounded border border-border-strong bg-surface-alt">
        <span className="absolute bottom-1 right-1 font-mono text-[8px] text-tertiary-fg">p.{hit.page_num}</span>
      </div>
      <div className="min-w-0 flex-1">
        <span className={`mb-1 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${chipClass(hit.page_type)}`}>
          {hit.page_type ?? "unknown"}
        </span>
        <p className="line-clamp-2 text-xs text-muted-fg">{hit.page_summary ?? "No summary."}</p>
        {hit.entities.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {hit.entities.slice(0, 5).map((e, i) => (
              <span key={i} className="rounded bg-info-bg px-1.5 py-px font-mono text-[10px] text-info">
                {e.value}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
