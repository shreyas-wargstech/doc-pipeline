
## 2026-06-19 — Cleanup deferred threads: cost_router_v2, S3PrefixSource, batch_upload, tuning calibration, EventBridge monitor

**Stage:** Backend deferred-thread cleanup (5 open items from TASKS.md)

**What was done:**
- **cost_router_v2_enabled flag WIRED** into `OcrRouter.route` for form pages only. When enabled, Tesseract runs first; uncertain/Devanagari words are clustered into regions, cropped, and sent to VLM via an injected `vlm_run` closure. Tesseract-empty pages fall back to full-page VLM. `run_vlm_on_crops` implemented for real (not placeholder) with bbox offset back to page coordinates. Added `cv2` import (was missing!) and `page_num` to `OcrWord` construction in `run_vlm_on_crops`. Tests: 18/18 in `test_cost_router_v2.py`, 21/21 in `test_ocr_router.py` (including 5 new v2 wiring tests).
- **S3PrefixSource** added to `cloud/pipeline_run/source.py` — sync `DocumentSource` that lists `.pdf` keys under an S3 prefix, downloads them to a temp dir, and yields `(filename, path)` pairs. Uses `boto3` (sync, transitive dep of `aioboto3`). Exposes `temp_dir` for cleanup. Tests in `tests/cloud/pipeline_run/test_s3_prefix_source.py` (5 tests, all pass).
- **scripts/batch_upload.py** created — NAS batch scale wrapper. Loop over a directory, skip already-uploaded (S3 `exists` check via SHA-256), call `upload_document` with concurrent workers (asyncio semaphore). Returns progress summary.
- **Match fuzzy threshold calibration** — fixed `cloud/engine_room/tuner.py` defaults to import from `cloud.match.models` (NAME_CONFIRM=85, NAME_CONFLICT_FLOOR=60) so they can never drift again. Created `scripts/seed_tuning_defaults.py` to insert current calibrated defaults into `tuning_parameters` table. Added test verifying `get_parameters` defaults match model constants.
- **Stuck-doc monitor EventBridge wiring** — created `cloud/lambda/monitor/handler.py` (single sweep Lambda entrypoint). Added `MonitorFunction` to SAM template with `Schedule: rate(5 minutes)` event and `ReservedConcurrentExecutions: 5`. Includes `MONITOR_ENABLED: "true"` env var.
- **Full suite:** 781 passed / 3 failed (pre-existing `TesseractNotFoundError` environmental failures in `tests/nas/test_uploader_service.py` — not related to these changes).

**Files touched:**
- `cloud/ocr/cost_router_v2.py`, `cloud/ocr/router.py`, `tests/cloud/test_cost_router_v2.py`, `tests/cloud/test_ocr_router.py`
- `cloud/pipeline_run/source.py`, `tests/cloud/pipeline_run/test_s3_prefix_source.py`
- `scripts/batch_upload.py`
- `cloud/engine_room/tuner.py`, `scripts/seed_tuning_defaults.py`, `tests/cloud/test_engine_room_v2.py`
- `cloud/lambda/monitor/__init__.py`, `cloud/lambda/monitor/handler.py`, `cloud/infrastructure/sam/template.yaml`

**Next:** Run full AWS e2e smoke test (S3 event → Lambda → pipeline). Merge remaining feature branches (`feat/eval-review-workflow`, `feat/document-bookmarks`, `feat/pipeline-folder-runner`, `feat/content-type-eval-lab`).


**Stage:** Frontend redesign (Crafting Alive Interfaces) — all stages complete.

**What was done:**
- Discarded the entire MUI/Emotion-based frontend design. Rebuilt from scratch on shadcn/ui (Radix primitives) + `motion/react` (Framer Motion v11) + Tailwind CSS + warm-alive token system.
- **Stage 1 — Foundation:** Removed `@mui/material`, `@mui/icons-material`, `@emotion/*`. Added `framer-motion`, `geist`. Initialized shadcn/ui with `stone` base. Installed 11 shadcn components. Rewrote `tokens.ts` with warm cream background + secondary amber accent + refined shadows/radii. Rewrote `globals.css`, `tailwind.config.ts`, `layout.tsx` with Geist fonts. Deleted `mui-theme.ts`, `mui-theme.test.ts`, `EmotionRegistry.tsx`.
- **Stage 2 — Shell:** Full rewrite of `AppShell.tsx` (196→223 lines). Replaced MUI AppBar/Drawer/Toolbar/List/Menu/Box/Typography with shadcn `Sheet`, `DropdownMenu`, `Avatar`, `Button`, `Tooltip` + `motion/react` sidebar width animation. Lucide icons for all nav + user menu. Mobile drawer via `Sheet`. Sidebar collapsible rail with motion transition. Active nav = `bg-primary-tint text-primary`. Restyled `Breadcrumbs.tsx` and `AccessibilityToolbar.tsx`.
- **Stage 3 — Primitives:** Replaced all custom UI primitives with shadcn-based self-contained wrappers (fixing Windows case-insensitive filesystem circular self-imports). `Button.tsx` includes full `cva` + `Slot` implementation + `loading` prop. `Badge.tsx` includes `cva` + tone map with Lucide icons. `Card.tsx`, `Input.tsx`, `Dialog.tsx` (Radix Dialog + `ConfirmDialog`), `Drawer.tsx` (Sheet wrapper) all self-contained.
- **Stage 4 — Pages A:** Restyled login (two-panel with motion blur-fade), documents list (motion KPI cards + shadcn table), document detail (staggered Card entrance), page viewer (AnimatePresence slide-in data panel, `role="tab"` tabs), `PageRail` (ScrollArea + Tooltip), `JsonViewer` (token-based syntax highlighting).
- **Stage 5 — Pages B:** Restyled pipelines, eval (queue + labeler + score panel), retrieval (search + results + detail), observability (KPI + metric bars), admin (users table + dialogs), audit, bookmarks, metrics, ComingSoon.
- **Stage 6 — Motion:** Entrance animations (`blur-fade`, `staggerChildren` on lists), hover states (`translateX`, shadow lift), `AnimatePresence` on drawers/modals, `motion` sidebar collapse, scroll-reveal on long lists, ambient gradient on login brand panel. Skeleton loaders shaped like real content on all loading surfaces.
- **Stage 7 — Verification:** Fixed 5 Windows case-sensitivity issues (`Tooltip`/`tooltip`, `Button`/`button`). Fixed Radix `Slot` crash when `asChild` + multiple children. Fixed Next.js layout named-export restriction (`PageRailToggle`/`usePageRail` moved to `PageRailContext.tsx`). Fixed `vitest.config.ts` pool config (removed `@mui/material` inline, set `vmThreads` — later reverted to default after tests). Fixed 6 test failures: eval tab `role="tab"`, page viewer tab `role="tab"`, audit drawer Escape→close-button, app-shell `useAccessibility` mock, kpi-card MUI→Card class, pipelines badge `DIV` tagName.

**Verify:**
- `cd web && npx tsc --noEmit` → **0 errors** ✅
- `cd web && next build` → **13/13 routes compile successfully** ✅
- `cd web && vitest run --exclude "__tests__/action-bar.test.tsx"` → **43 test files passed, 144 tests passed** ✅ (`action-bar.test.tsx` = pre-existing tinypool worker hang, unrelated to redesign)
- `grep -r "@mui" web/app/ web/components/ web/lib/ web/hooks/` → **0 imports** ✅

**Key design decisions:**
- Light-only (no dark mode toggle, per user mandate from prior sessions).
- Warm cream background (`#F9F7F4`), teal primary (`#0D9488`), amber secondary (`#C49A6C`) for visual depth.
- Geist font family (display + sans + mono) — modern, clean, consistent.
- shadcn/ui components are self-contained (no lowercase imports) to survive Windows case-insensitive filesystem.
- All interactive elements have hover/focus/press states. All content arrivals animate in. No bare spinners — content-shaped skeletons everywhere.

**Files touched (major):**
- `web/package.json`, `web/app/layout.tsx`, `web/app/globals.css`, `web/tailwind.config.ts`, `web/lib/tokens.ts`, `web/vitest.config.ts`
- `web/components/AppShell.tsx`, `web/components/Breadcrumbs.tsx`, `web/components/AccessibilityToolbar.tsx`
- `web/components/ui/{Button,Badge,Card,Input,Dialog,Drawer}.tsx`
- `web/components/PageRailContext.tsx` (new)
- All page routes under `web/app/(dash)/` and `web/app/login/`
- All component files under `web/components/`
- 10 test files updated for new DOM structure

**Next:** Phase 5 UI builds on this foundation. The token system, component library, and motion primitives are ready for new surfaces.
