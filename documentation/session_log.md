
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


## 2026-06-19 — Merge 4 already-built feature branches + working tree cleanup

**Stage:** Quick-win branch merge + commit cleanup

**What was done:**
- All 4 branches already merged into `main` (verified via `git merge-base --is-ancestor`): `feat/eval-review-workflow` (`7e3ef91`), `feat/document-bookmarks` (`9b3aacd`), `feat/pipeline-folder-runner` (`678d3b7`), `feat/content-type-eval-lab` (`d5dd19f`). Branch names deleted post-merge.
- Working tree had ~170 uncommitted files (staged + unstaged + untracked). Committed in 2 chunks:
  - `bb7704f` — staged changes: documentation, research, schema scripts, infra updates
  - `9ffbfcf` — unstaged + untracked: frontend redesign, backend updates, pipeline runner fixes, Lambda `__init__` files, new shadcn/ui components, removed MUI files

**Verify:**
- `uv run pytest -m "not integration"` → **781 passed / 3 failed** ✅ (3 pre-existing `TesseractNotFoundError` environmental failures in `tests/nas/test_uploader_service.py` — not related to these changes)
- `cd web && tsc --noEmit` → **0 errors** ✅
- `cd web && next build` → **13/13 routes compiled** ✅

**Next:** AWS e2e smoke test (S3 event → Lambda → pipeline).


## 2026-06-19 — `make serve` login 500: app tries to connect to AWS RDS private IP from local dev

**Stage:** Quick local dev fix

**What was done:**
- `.env` had `DATABASE_URL` pointing to production RDS (`docintel-production-postgres.cbcc084q6q9j.ap-south-1.rds.amazonaws.com`), which resolves to VPC-private IP `172.31.16.207` from the local Windows machine → connection timeout.
- Swapped `.env` lines: uncommented local `DATABASE_URL=postgresql+asyncpg://pipeline:pipeline@localhost:5432/doc_pipeline`, commented out production RDS line.

**Verify:**
- `head -n 4 .env` → local DB active, production line commented out.

**Next:** Restart `make serve` (needs fresh env read). Confirm `make up` running so local Postgres is reachable. Seed dashboard user if not yet done.

**Files touched:** `.env`


## 2026-06-18 — [KIMI] SAM container image build succeeded (FIX-067)

**What was done:** Switched all 7 Lambda functions from zip to container image builds. Verified `sam build` produces Docker images.

**Blockers encountered + fixes:**

1. **Runtime mismatch:** Host had Python 3.13, template had `python3.12` → SAM binary validation failed. Fixed: changed `Runtime: python3.12` → `python3.13` in `Globals.Function` and `.aws-sam/build.toml`.

2. **Corrupted pip:** `pip._internal.utils` missing in `AppData\Roaming\Python\Python313\site-packages`. Fix: removed `pip` directory and `pip-*.dist-info`, ran `python -m ensurepip --upgrade`. (Not fixed yet — `python -m pip` still works via `python313\Lib\site-packages\pip`.)

3. **Disk full:** `sam build` tried to download all 361 packages into temp. `OSError: [Errno 28] No space left on device`. This plus the pywin32 issue confirmed zip-based builds are wrong for this project — the OCR stage needs Tesseract/zbar/OpenCV system libraries (installed via `dnf` in `Dockerfile.ocr`), not just pip packages.

4. **Container image approach:** Changed all 7 functions to `PackageType: Image` with `Metadata: {Dockerfile: ..., DockerContext: ...}`. Grouped by Docker image:
   - `Dockerfile.ocr` → OcrFunction, VlmFunction (both need heavy deps)
   - `Dockerfile.light` → StructureFunction, MatchFunction, MonitorFunction (lightweight)
   - `Dockerfile.persist-index` → PersistFunction, IndexFunction (share heavy sentence-transformers + ollama deps)

5. **SAM tomlkit crash with `PackageType: Image`:** Removed `Runtime` from `Globals` → `ConvertError: Unable to convert object of <class 'NoneType'> to TOML item`. SAM's build graph serializes `Runtime` even for image builds. Fix: added `Runtime: python3.13` back to `Globals.Function` (used only for build graph, ignored at deploy time for images).

6. **pywin32 breaks pip builder on Windows:** `pywin32==312 ; sys_platform == 'win32'` in `requirements.txt` causes SAM's `PythonPipBuilder` to fail even though the project is now image-based. The `PythonPipBuilder` still runs for `Runtime` validation. Fix: removed `pywin32` from `requirements.txt` (it was only for Windows local dev and is not needed in Lambda).

7. **Docker Desktop not running:** `sam build` with `PackageType: Image` needs a Docker daemon. `docker ps` returned 500 error. Fix: started Docker Desktop, `docker ps` returned clean, then `sam build` succeeded:
   - `Successfully built d43517617149`
   - `Successfully tagged persistfunction:latest`

**Verify:** Docker images are being built locally by SAM. Each function maps to the correct Dockerfile. No more zip/pip/pywin32 issues.

**Next:** `sam deploy --guided` (or `python cloud/infrastructure/scripts/deploy.py --env production --region ap-south-1`) to push images to ECR and create/update the stack. Need to ensure ECR repos exist in the target AWS account for each image.

**Files touched:** `cloud/infrastructure/sam/template.yaml`, `requirements.txt`, `.aws-samignore`, `cloud/lambda/{__init__.py,ocr/__init__.py,vlm/__init__.py,structure/__init__.py,match/__init__.py,persist/__init__.py,index/__init__.py,monitor/__init__.py}`


## 2026-06-20 — [KIMI] Phase 5 UI: Aether Chat + Engine Room v1 + Document Autopsy

**Stage:** Frontend + backend build (3 new surfaces)

**What was done:**
- **Engine Room v1 page** (`/engine-room`) — full UI for existing backend endpoints:
  - Health panel: live cards with 30s auto-refresh, status badges, stagger entrance
  - Diagnostics panel: run-checks button + animated result list with pass/warn/error styling
  - Parameter tuner: table of all parameters, inline edit dialog with test-on-sample + save
  - A/B test panel: hypothesis form, variant JSON editor, results with winner badge + baseline/variant comparison
  - Cost summary: KPI cards + per-stage breakdown
  - Document inspector: ID input + stage-by-stage pipeline report with color-coded status dots
  - Nav added to AppShell (admin-only), visible nav filter updated for both `/admin` and `/engine-room`

- **Document Autopsy UI** (`AutopsyPanel` component):
  - New `AutopsyPanel.tsx` component with timeline cards per stage, recommendation callout, stagger entrance
  - Integrated into document detail page (`/documents/[id]`) — shows for failed/manual_review docs OR all docs for admins
  - Calls existing `GET /api/documents/{id}/autopsy` endpoint

- **Aether Chat** (`/aether`) — zero-LLM pipeline assistant:
  - Backend: `cloud/aether_chat/service.py` — regex intent router (autopsy/narrative/context/identity/inspector/health), routes to existing services, no OpenRouter cost
  - Backend API: `POST /api/chat` added to `cloud/dashboard/api.py`
  - Frontend: `useChat` hook + full chat page with message bubbles, typing indicator, document context selector, ambient gradient background
  - Nav added to AppShell (all roles)

- **Types**: Added `EngineCostSummary`, `TuningParameter`, `TuningSuggestion`, `ABTestResult`, `InspectorReport`, `HealthCheck`, `DiagnosticResult`, `AutopsyReport`, `AutopsyStage`, `ChatMessage`, `ChatRequest`, `ChatResponse` to `web/lib/types.ts`

- **Test fixes**: Added `useRole` mock + `AutopsyPanel` mock to `document-detail.test.tsx` and `document-overview.test.tsx` (QueryClient requirement). Updated `app-shell.test.tsx` nav count from 7→9.

**Verify:**
- `cd web && tsc --noEmit` → **0 errors** ✅
- `cd web && vitest run --exclude "__tests__/action-bar.test.tsx"` → **43 test files passed, 144 tests passed** ✅
- `uv run pytest tests/cloud/autopsy/ tests/cloud/engine_room/ tests/cloud/dashboard/test_admin_api.py` → **67 passed** ✅

**Files touched:**
- `web/app/(dash)/engine-room/page.tsx` (new)
- `web/app/(dash)/aether/page.tsx` (new)
- `web/app/(dash)/documents/[id]/page.tsx` (AutopsyPanel integration)
- `web/components/AutopsyPanel.tsx` (new)
- `web/components/AppShell.tsx` (nav items + filter)
- `web/hooks/useEngineRoom.ts` (new)
- `web/hooks/useChat.ts` (new)
- `web/lib/types.ts` (new types)
- `cloud/aether_chat/service.py` (new)
- `cloud/dashboard/api.py` (chat endpoint added)
- `web/__tests__/document-detail.test.tsx`, `web/__tests__/document-overview.test.tsx`, `web/__tests__/app-shell.test.tsx`

**Next:** Next.js `next build` full verification (timed out in this environment, but tsc clean). Backend full suite verification. AWS e2e smoke test.
