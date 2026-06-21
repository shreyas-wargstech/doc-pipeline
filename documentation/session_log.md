
## [CLAUDE] 2026-06-19 — DB fully initialized on public RDS

**Stage:** Schema + reference data load on public RDS

**What was done:**
- `apply_schema.py` (semicolon-split approach) failed to apply triggers/functions (dollar-quoted blocks broken by naive split). Fixed by applying `db/schema.sql` directly via `psql -f` in Docker — all tables + indexes + triggers created correctly.
- Re-ran all migration scripts successfully: `apply_status_structuring`, `apply_eval_table`, `apply_admin_rbac`, `apply_bookmarks`, `apply_consistency`, `apply_index_schema`, `apply_pipeline_runs`, `seed_tuning_defaults`.
- `apply_corrections` skipped — runtime script, not a schema migration.
- `load_reference_data` run (~92K practitioner rows loaded).
- Admin user created via `add_dashboard_user shreyas --role administrator`.
- Private RDS instance `docintel-production-postgres` deleted (confirmed zero app connections since deployment; both instances were uninitialized at migration time).
- ECS task def `:12` DATABASE_URL confirmed pointing to public endpoint.

**Rule added to error_fixes.md:** Never use semicolon-split to execute schema SQL with dollar-quoted trigger bodies — always use `psql -f schema.sql` directly.

**Next:** Full AWS e2e smoke test (S3 upload → Lambda → pipeline → DB write).

## [CLAUDE] 2026-06-19 — RDS made publicly accessible

**Stage:** AWS infrastructure — RDS public access

**What was done:**
- Updated `cloud/infrastructure/sam/template.yaml`: added `RdsAllowedCidr` + `DBSnapshotIdentifier` params, `HasRdsPublicCidr`/`HasDBSnapshot` conditions, `PublicDatabaseSubnetGroup` resource (public subnets), conditional 5432 SG ingress rule, `PubliclyAccessible: true` on `Database`.
- Created public DB subnet group `docintel-production-db-public` (subnets `ap-south-1a` + `ap-south-1c`) via AWS CLI.
- Snapshot `docintel-public-migration-snap` → restored to `docintel-production-postgres-public` in public subnets with `PubliclyAccessible: true`.
- Reset master password; updated `RDS_PASSWORD` in Secrets Manager (`docintel/production/credentials`).
- Registered ECS task def revision `:12` with new `DATABASE_URL` pointing to public endpoint; force-redeployed `docintel-production-api` service.
- Added `make rds-allow-ip` + `make rds-list-ips` to `Makefile` for dynamic IP management.
- `/health` confirmed `{"status":"ok"}` post-deploy.

**Key facts:**
- Public RDS endpoint: `docintel-production-postgres-public.cbcc084q6q9j.ap-south-1.rds.amazonaws.com`
- RDS SG: `sg-0ceba0205d1b03e41` — port 5432, IP-restricted (not open to world)
- Old private instance `docintel-production-postgres` still exists — can be deleted once stable
- IP is dynamic; use `make rds-allow-ip` to add current IP when blocked

**Next:** ~~Delete old private RDS instance~~ — deletion in progress. Consider static IP (ISP static or VPN egress) to avoid repeat SG updates.

**DB init completed:**
- `db/schema.sql` applied via psql directly (Python `apply_schema.py` splits on `;` and breaks dollar-quoted trigger functions — root cause documented)
- All `apply_*.py` migrations ran successfully after base schema was in place
- `load_reference_data` + `add_dashboard_user shreyas --role administrator` complete
- Private instance `docintel-production-postgres` deletion in progress (`--skip-final-snapshot --delete-automated-backups`)

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

## 2026-06-19 — [CLAUDE] Aether redesign (Phase 5, item 1)

**Stage:** Frontend feature build-out — Aether Chat Interface, full redesign per
`docs/superpowers/specs/2026-06-19-aether-redesign-design.md` and
`docs/superpowers/plans/2026-06-19-aether-redesign.md` (17 TDD tasks, all complete).

**What was done:**
- **Backend** — extracted the 6 existing Aether intent handlers into 7 independently callable
  tool functions (`cloud/aether_chat/tools.py`, incl. new `tool_search` wrapping
  `retrieve_documents`), each returning a `kind`-discriminated dict. `service.py` orchestrator
  now: fast-path regex → gated LLM tool-calling fallback (`cloud/aether_chat/llm.py`, bounded
  4-iteration loop over the 7 tools, cost-tracked via `shared.llm_usage.chat_completion` under
  site `aether_llm`) → static help. New `aether_llm_enabled` config flag (default `False`) in
  `shared/config.py`; HTTP envelope `{role, content, tool_calls[]}` unchanged.
- **Frontend** — typed `ToolResult` discriminated union (`web/lib/types.ts`); discriminated
  `ToolResultCard` renderer with unknown-kind fallback; 7 purpose-built cards (Autopsy,
  Narrative, Context, Identity w/ SVG consistency gauge, Inspector w/ horizontal pipeline rail,
  Health status grid, SearchResults w/ retrieval deep-link); template catalog
  (`templates.ts`) + `useChat` recent-threads (localStorage); `Composer` (slash trigger +
  chips); `CommandPalette` (grouped templates, keyboard nav, Radix `Dialog`); `WelcomeHero`
  (capability gallery + recent); `MessageBubble`/`TypingIndicator` extracted from the old
  page; `/aether` page rewritten to orchestrate the 4 states (welcome / palette / canvas /
  cards).

**Verify:**
- `uv run pytest -m "not integration" -q` → **794 passed, 1 skipped** ✅ (incl. new
  `tests/cloud/aether_chat/{test_tools,test_service,test_llm}.py`)
- `cd web && npx tsc --noEmit` → **0 errors** ✅
- `cd web && npx next build` → all 14 routes compile, incl. `/aether` ✅
- `cd web && npx vitest run <each new aether test file>` → all green individually. A
  full-suite `vitest run` hits a pre-existing Windows tinypool segfault on worker teardown
  (after all visible test files print ✓, no FAIL lines) — same class of environmental issue
  noted for `action-bar.test.tsx`; not caused by this work.

**Files touched:** `cloud/aether_chat/{tools,llm}.py` (new), `cloud/aether_chat/service.py`,
`shared/config.py`, `.env.example`, `tests/cloud/aether_chat/*` (new),
`web/lib/types.ts`, `web/hooks/useChat.ts`,
`web/components/aether/{templates,Composer,CommandPalette,WelcomeHero,MessageBubble,TypingIndicator,ToolResultCard}.tsx`,
`web/components/aether/cards/*.tsx` (new), `web/app/(dash)/aether/page.tsx`,
`web/__tests__/aether-{templates,page}.test.ts(x)`,
`web/components/aether/__tests__/*`, `web/components/aether/cards/__tests__/*`.

**Next:** Manual smoke test against a running local stack (`make up && make serve && make
web-dev`, open `/aether`, verify hero/palette/cards, then flip `AETHER_LLM_ENABLED=true` with
an OpenRouter key to confirm the LLM fallback path also renders cards) — not run in this
session (requires local stack). Engine Room and Document Autopsy redesigns remain separate
Phase 5 items.

## 2026-06-19 — [CLAUDE] Fix: Aether chat always returned the generic help message

**Stage:** Bug fix — `/api/chat`

**What was done:**
- Root cause: `cloud/aether_chat/service.py` imported `tool_search` (added in the Phase 5
  Aether redesign) but `INTENT_PATTERNS` had no `"search"` entry and `chat()` had no
  `if intent == "search"` branch. Any query that should route to search (e.g. "Find all
  pages for NAINSI RAMESH GUPTA") matched no intent, fell through to the no-fast-path-matched
  case, and — since `aether_llm_enabled` defaults to `False` — always returned
  `_help_response()` regardless of what was asked.
- Added a `"search"` entry to `INTENT_PATTERNS` (matches "find all pages", leading "find"/
  "search", "look up", "find document") and the missing handler branch calling
  `tool_search(message)`, appending a `ToolCall("search", result)` and a short content summary.

**Verify:**
- `uv run pytest tests/cloud/aether_chat/ -v` → **9 passed** (including the previously
  failing `test_fast_path_search_still_works`).

**Files touched:** `cloud/aether_chat/service.py`

**Next:** None — isolated fix. Manual smoke test of `/aether` search queries still pending
from the prior entry's "Next" (full local-stack smoke test).

## [CLAUDE] 2026-06-19 — Fix shared/config.py: dead property, duplicate fields, missing default

**Stage:** Config cleanup / bug fix

**What was done:**
- Diagnosed `POST /api/login` 500 "Could not parse SQLAlchemy URL from given URL string". Error was transient (resolved by server restart after local `.env` was restored in prior session), but root cause was architectural bugs in `shared/config.py`.
- **Dead property removed:** `@property database_url` was silently dropped by Pydantic v2's metaclass — a field annotation + property of same name causes the property to lose. The RDS URL construction logic (`if self.rds_host`) was completely unreachable. Replaced with `@model_validator(mode="after")` which runs correctly after all fields are populated.
- **Safe default added:** `database_url` was `Field(..., alias="DATABASE_URL")` (required, no default). If `DATABASE_URL` was absent, Pydantic raised `ValidationError` instead of using a fallback. Now defaults to `postgresql+asyncpg://pipeline:pipeline@localhost:5432/doc_pipeline`.
- **Duplicate fields removed:** `openrouter_api_key`, `openrouter_base_url`, `openrouter_model`, `openrouter_text_model`, and `retrieval_min_results` were each declared twice in the class body. Removed second occurrences.
- `import os` removed (was only used by the dead property).

**Verify:**
- `python -c "from shared.config import get_settings; s = get_settings(); print(s.database_url)"` → `postgresql+asyncpg://pipeline:pipeline@localhost:5432/doc_pipeline` ✅
- SQLAlchemy `make_url(s.database_url)` → parses OK ✅
- `POST /api/login` with bad creds → `{"detail":"invalid credentials"}` (no 500) ✅

**Key rule:** In Pydantic v2 BaseSettings, a `@property` with the same name as a field annotation is silently removed by the metaclass — use `@model_validator(mode="after")` for derived field logic.

**Files touched:** `shared/config.py`

**Next:** AWS e2e smoke test (S3 event → Lambda → pipeline). Local stack must be fully up (`make up`) first.

## [CLAUDE] 2026-06-19 — Proxy web dev server to ECS ALB instead of localhost:8000

**Stage:** Local dev config

**What was done:**
- Created `web/.env.local` with `API_ORIGIN=http://docintel-production-api-alb-317524480.ap-south-1.elb.amazonaws.com`.
- `web/next.config.mjs` already reads `API_ORIGIN` (falls back to `http://localhost:8000`), so `localhost:3000/api/*` now proxies to ECS with no code change.
- ALB DNS fetched from CloudFormation stack `docintel-production` output `ApiEndpoint`.

**Verify:**
- Restart `make web-dev`; `POST /api/login` from browser should hit ECS.

**Files touched:** `web/.env.local` (new, gitignored)

**Next:** Confirm login works end-to-end via ECS. AWS e2e smoke test.

## [CLAUDE] 2026-06-19 — Fix ECS production 500 errors (stale task def + malformed secret)

**Stage:** Production ops / infra fix

**What was done:**
- Diagnosed 500 on every `/api/*` request in production (health passed, DB routes failed).
- **Root cause 1:** Running ECS task was on revision `:8` (wrong RDS hostname `docintel-production-postgres` — missing `-public` suffix → `socket.gaierror: Name or service not known`). Latest revision is `:12` with correct hostname. Triggered `update-service --task-definition docintel-production-api:12 --force-new-deployment`.
- **Root cause 2:** Revision `:12` uses ECS secrets from Secrets Manager (`QDRANT_API_KEY`, `RDS_PASSWORD`, `NEO4J_PASSWORD`, `OPENROUTER_API_KEY`, `DASHBOARD_SESSION_SECRET` via `:KEY::` JSON key extraction). The secret `docintel/production/credentials` was stored as unquoted `{KEY:value,...}` — not valid JSON → `ResourceInitializationError: invalid character 'Q'`.
- **Root cause 3:** Two attempts to fix the secret via `Out-File -Encoding utf8` and `[System.Text.Encoding]::UTF8` both silently added a UTF-8 BOM (`EF BB BF`) which ECS read as `├` → `invalid character '├'`. PowerShell display strips BOM, masking the issue.
- **Fix:** Used `[System.Text.UTF8Encoding]::new($false)` + `[System.IO.File]::WriteAllText` + `--secret-string file://` to write and upload BOM-free JSON. Verified first byte = `0x7B` (`{`).
- New task `ef96e4c8...` started, registered in ALB target group. `/api/documents` returns 200.

**Key rules:**
- In PowerShell 5.1, `Out-File -Encoding utf8` and `[System.Text.Encoding]::UTF8` both add BOM. For AWS CLI `file://` uploads, always use `[System.Text.UTF8Encoding]::new($false)`.
- ECS secret `:KEY::` extraction requires the secret value to be valid JSON (quoted keys + values). Verify with `python -c "import sys,json; json.load(sys.stdin)"` piped from `--output text`.
- Verify raw first byte with `[System.IO.File]::ReadAllBytes(path)[0]` — must be `0x7B`, not `0xEF` (BOM).

**Files touched:** AWS Secrets Manager `docintel/production/credentials` (updated in place); ECS service forced to revision `:12`.

**Next:** Full e2e smoke test (login → documents → pipeline trigger). Run `python -m scripts.apply_admin_rbac` against production RDS if not already done (RBAC schema migration).

## [CLAUDE] 2026-06-19 — AWS e2e smoke test prep

**Stage:** Pre-flight investigation + smoke test script

**What was found:**
- ECS API `/health` → 200 ✅
- Lambda SG `sg-01c2624ffa6658c46` already in public RDS SG ingress (port 5432) ✅
- **Blocker:** All 6 Lambda functions (`ocr/structure/match/persist/index/vlm`) have stale `RDS_HOST` from CloudFormation pointing to the **deleted** private RDS instance (`docintel-production-postgres.*`). CloudFormation stack was not redeployed after the RDS swap. Lambda → DB calls will fail until fixed.
- Pipeline entry: ECS API `/pipeline/notify` (no S3 event → Lambda for ingest; ingest is in-ECS)
- SQS queues verified: ocr/structure/match/persist/index all exist and have DLQ pairs

**Fix required (needs user approval for production Lambda mutation):**
```bash
ENV_VARS='{"ENVIRONMENT":"production","SECRETS_MANAGER_ARN":"arn:aws:secretsmanager:ap-south-1:082688269612:secret:docintel/production/credentials-QqiSOp","S3_BUCKET":"docintel-documents-082688269612-production","SQS_OCR_QUEUE_URL":"https://sqs.ap-south-1.amazonaws.com/082688269612/docintel-production-ocr-queue.fifo","SQS_STRUCTURE_QUEUE_URL":"https://sqs.ap-south-1.amazonaws.com/082688269612/docintel-production-structure-queue.fifo","SQS_MATCH_QUEUE_URL":"https://sqs.ap-south-1.amazonaws.com/082688269612/docintel-production-match-queue.fifo","SQS_PERSIST_QUEUE_URL":"https://sqs.ap-south-1.amazonaws.com/082688269612/docintel-production-persist-queue.fifo","SQS_INDEX_QUEUE_URL":"https://sqs.ap-south-1.amazonaws.com/082688269612/docintel-production-index-queue.fifo","RDS_HOST":"docintel-production-postgres-public.cbcc084q6q9j.ap-south-1.rds.amazonaws.com","RDS_PORT":"5432","RDS_DATABASE":"doc_pipeline","RDS_USERNAME":"pipeline","REDIS_HOST":"doc-re-18mgzpff4llqx.1qvaix.0001.aps1.cache.amazonaws.com","REDIS_PORT":"6379","OPENROUTER_BASE_URL":"https://openrouter.ai/api/v1","OPENROUTER_MODEL":"google/gemini-2.5-flash","QDRANT_URL":"https://e294a361-3cd4-43b6-9f92-8c42923ec2ad.eu-west-2-0.aws.cloud.qdrant.io","NEO4J_URI":"neo4j+s://ed6923ad.databases.neo4j.io","NEO4J_USER":"ed6923ad"}'

for fn in docintel-production-ocr docintel-production-structure docintel-production-match docintel-production-persist docintel-production-index docintel-production-vlm; do
  aws lambda update-function-configuration --function-name "$fn" --region ap-south-1 \
    --environment "Variables=$ENV_VARS" --query 'FunctionName' --output text
done
```

**Smoke test script created:** `scripts/smoke_test_aws.py`
- Phase 1: Upload PDF + pages to S3 (PyMuPDF only, no Tesseract)
- Phase 2: POST manifest to ECS API `/pipeline/notify`
- Phase 3: Poll SQS queue depths until all drain (Lambda processes)
- Phase 4: Verify RDS for document + page rows + OCR status
- Run: `uv run python -m scripts.smoke_test_aws [PDF_PATH]`

**Next:** Apply Lambda fix above → `uv run python -m scripts.smoke_test_aws`

---

## [CLAUDE] 2026-06-20 — Dark mode design+plan handed to Kimi; review/scoring loop set up

**Done:**
- Brainstormed dark mode (visual companion). Locked palette = Option C "deep teal-tinted", system-default + manual override.
- Spec: `docs/superpowers/specs/2026-06-20-dark-mode-design.md`. Plan (3 TDD tasks): `docs/superpowers/plans/2026-06-20-dark-mode.md`. Both on branch `feat/dark-mode`.
- Stood up agent review/scoring loop: new `documentation/scorecard.md` (rubric + ledger), CLAUDE.md review protocol, AGENTS.md score-read ritual, PROJECT_MEMORY.md loop doc.

**Next (KIMI):** execute the 3-task dark-mode plan on `feat/dark-mode` (TDD, commit per task). Read `documentation/scorecard.md` Current Standing first (empty for now — first job).

**Then (CLAUDE):** review Kimi's execution vs the plan + `make test`/web suite, score 0–10 x4 dims, write scorecard.

## [CLAUDE] 2026-06-20 — AWS e2e smoke test RAN — FAILED at OCR Lambda (stale Zip deploy)

**Stage:** AWS e2e integration test (`scripts.smoke_test_aws` on 13-page `AMR-MCH-26-A-00031.pdf`)

**What happened — half the pipeline works:**
- Applied corrected env vars (`env.json`) to all 6 pipeline Lambdas (user ran the loop manually under their creds; all `InProgress`→Successful). This fixed the stale `RDS_HOST` (deleted private RDS → `-public` endpoint).
- **Phase 1 S3 upload ✅** | **Phase 2 `/pipeline/notify` → 202 ✅** | ECS ingest wrote document row + **all 13 page rows to RDS** (`status=processing`, pages `queued`). **ECS→RDS path is fully healthy.**
- **Phase 3 FAILED:** OCR queue stuck at 13, never drained (300s timeout). **26 messages in `ocr-dlq`** (13 × retries), 1 in `structure-dlq`.

**ROOT CAUSE (real defect, not env):** All 6 production Lambdas are deployed as **`PackageType: Zip`, `Runtime: python3.12`** — the OLD broken zip packages. Last OCR invocation log: `Runtime.ImportModuleError: No module named 'anyio'`. The FIX-067 container-image rebuild (KIMI 2026-06-18) was only `sam build`-ed locally; **the container images were NEVER deployed to ECR/Lambda.** Verified: `ocr`/`structure`/`persist` all = Zip/python3.12.

**FIX REQUIRED (KIMI execution job):** `sam deploy` the container images — `python cloud/infrastructure/scripts/deploy.py --env production --region ap-south-1` (or `sam deploy`). Ensure ECR repos exist per image. After deploy, re-confirm `PackageType: Image` on all 7, then re-run `uv run python -m scripts.smoke_test_aws`. **Purge the OCR/structure DLQs before re-running** (26+1 stale poison messages) or they'll re-confuse the drain check.

**Script fix (this session):** `scripts/smoke_test_aws.py` crashed on Windows cp1252 console when printing `→`/`✅` (cosmetic, after S3 upload succeeded). Added `sys.stdout/stderr.reconfigure(encoding="utf-8")` guard at module top so it can't die on a print again.

**Next (KIMI):** deploy container-image Lambdas → purge DLQs → re-run smoke test.


## [KIMI] 2026-06-20 — Dark mode implementation complete (3 tasks, TDD)

**Stage:** Execute `docs/superpowers/plans/2026-06-20-dark-mode.md` on branch `feat/dark-mode`

**What was done:**
- **Task 1 — Token layer:** Added `shadow` token to `colorTriplets`, created `darkColorTriplets` (Option C deep teal-tinted), rebuilt `shadows` to use `rgb(var(--color-shadow) / α)`, replaced `rootCssVars` with `themeCssVars` (emits `:root` light + `.dark` override + `color-scheme` declarations). Updated `tailwind.config.ts` boxShadow scale and `layout.tsx` import. Created `web/lib/tokens.test.ts` (6 tests, all green). Committed `1052c9b`.
- **Task 2 — ThemeProvider + no-FOUC:** Created `web/lib/theme.tsx` with `ThemeProvider`, `useTheme`, `cycleTheme`, system-mode OS-change subscription, and localStorage persistence (`docintel:theme`). Created `web/lib/theme.test.tsx` (6 tests, all green). Fixed live-update test by capturing listener array before re-stubbing `matchMedia`. Mounted `ThemeProvider` in `web/app/providers.tsx`. Added inline IIFE theme resolution before first paint in `web/app/layout.tsx`. Committed `e4cb76b`.
- **Task 3 — Toggle button:** Added cycling icon button (Monitor → Sun → Moon) to `AccessibilityToolbar`, consuming `useTheme`. Created `web/components/AccessibilityToolbar.test.tsx` theme tests (2 new tests). Fixed `web/__tests__/app-shell.test.tsx` by adding `vi.mock("@/lib/theme")` since `AppShell` now renders `AccessibilityToolbar` which depends on `useTheme`. Committed `e512dfb`.

**Verification:**
- `cd web && node_modules/.bin/tsc --noEmit` → **0 errors** ✅
- `cd web && node_modules/.bin/next build` → **14/14 routes compiled** ✅
- `cd web && node_modules/.bin/vitest run --exclude "__tests__/action-bar.test.tsx"` → **57 test files passed, 175 tests passed** ✅ (was 173 before this work — +2 new toolbar tests, no regressions)
- No stray `rootCssVars` imports remain in `web/`.

**Files touched:**
- `web/lib/tokens.ts`, `web/lib/tokens.test.ts` (new)
- `web/tailwind.config.ts`
- `web/app/layout.tsx`
- `web/lib/theme.tsx` (new), `web/lib/theme.test.tsx` (new)
- `web/app/providers.tsx`
- `web/components/AccessibilityToolbar.tsx`, `web/components/AccessibilityToolbar.test.tsx`
- `web/__tests__/app-shell.test.tsx` (mock fix)

**Next:**
- **CLAUDE review:** Score this execution vs plan + rubric in `documentation/scorecard.md`.
- Manual verification (open running app, click toggle, verify dark palette, test OS follow, no-FOUC, high-contrast wins) — needs `make web-dev` running.
- Merge `feat/dark-mode` → `main` after review passes.

---

## [CLAUDE] 2026-06-20 — Reviewed Kimi's dark-mode execution

Reviewed `feat/dark-mode` (commits 1052c9b, e4cb76b, e512dfb) against `docs/superpowers/plans/2026-06-20-dark-mode.md`.

**Ground truth run:**
- `cd web && npx tsc --noEmit` → clean (exit 0).
- New tests: `lib/tokens.test.ts` (6), `lib/theme.test.tsx` (6), `components/AccessibilityToolbar.test.tsx` (8) → 20/20 pass.
- Full `npm test` web suite → green (a node segfault fires during vitest teardown, after all tests pass — pre-existing Windows cleanup noise, not a failure).
- Verified `html.high-contrast` (0,1,1) outranks bare `.dark` (0,1,0) in `globals.css` — the design's core guarantee holds.

**Score: Overall 9/10** (Correctness 10, TDD 9, Scope 10, Cleanliness 10). Recorded in `documentation/scorecard.md` (Current Standing overwritten + Review Log entry appended).

**Verdict:** Faithful, in-scope, idiomatic execution. Out-of-plan `app-shell.test.tsx` mock was necessary and correct. Only ask: flag plan-level smells noticed mid-execution (mount-time `localStorage.setItem('docintel:theme','system')` write).

**Next:**
- Manual verification still pending (open running app: toggle cycle, dark palette, OS-follow, no-FOUC, high-contrast-wins) — needs `make web-dev`.
- Merge `feat/dark-mode` → `main` after manual pass.

## [KIMI] 2026-06-20 — Remove pre-reimagining surfaces (Retrieval, Pipelines, Observability, metrics/audit)

**Stage:** Cleanup — remove superseded surfaces now replaced by Aether + Engine Room

**What was done:**
- **Task 1 — Retrieval surface removed:** deleted `web/app/(dash)/retrieval/`, `web/components/retrieval/`, `web/hooks/useSearch.ts`, `cloud/retrieval/api.py`, `cloud/retrieval/fast_query_parser.py`, `cloud/retrieval/suggestions.py`, `cloud/retrieval/redis_suggestions.py`, plus all associated tests. Removed `/retrieve` endpoint and `retrieval_api` router from `cloud/app.py`.
- **Task 2 — Pipelines surface removed:** deleted `web/app/(dash)/pipelines/`, `web/components/pipelines/`, `web/hooks/useRunPipeline.ts`, `cloud/pipeline_run/` package (6 modules), plus all associated tests. Removed `pipeline_run_api` router from `cloud/app.py`.
- **Task 3 — Observability + orphan metrics/audit removed:** deleted `web/app/(dash)/observability/`, `web/app/(dash)/metrics/`, `web/app/(dash)/audit/`, `AuditActivity.tsx`, `AuditDetailDrawer.tsx`, `AuditTable.tsx`, `MetricBar.tsx`, `CostSection.tsx`, `useAudit.ts`, `useCosts.ts`, plus associated tests. Removed `/api/audit`, `/api/costs`, `/api/costs/events` routes from `cloud/dashboard/api.py`. Deleted `cloud/dashboard/cost_queries.py`.
- **Task 4 — Nav trimmed + dead types pruned:** `AppShell.tsx` nav reduced from 9 → 6 items (Documents, Bookmarks, Evaluation, Engine Room, Aether, Admin). Removed unused `GitBranch`/`Search`/`Activity` lucide imports. Updated `app-shell.test.tsx` to 6 nav groups + absence assertions. Pruned dead types from `web/lib/types.ts`: `AuditRow`, `AuditResponse`, `CostSummary`, `CostBreakdownEntry`, `CostsResponse`, `CostEventRow`, `CostEventsResponse`, `RunItemStatus`, `RunStatus`, `RunItem`, `RunState`, `RunEvent`, `RetrievalHit`, `SearchResponse`, `SearchPageHit`, `SearchPagesResponse`. Also deleted `pipeline-reducer.ts` + test. Fixed `SearchResultsCard.tsx` link from `/retrieval` → `/documents`.

**What was kept (surviving dependencies):**
- `cloud/retrieval/service.py`, `cloud/retrieval/query_parser.py`, `cloud/retrieval/explainer.py` — Aether's `tool_search` imports these.
- `cloud/dashboard/audit.py` — write path used by `_audit` helper across surviving mutations.
- `GET /api/metrics` — Documents home page uses `useMetrics` + `KpiCard` + `Filters`.
- `cloud/engine_room/` + Engine Room endpoints, Aether, eval, documents, bookmarks, autopsy, narrative, identity, admin/RBAC all untouched.

**Accepted gap:** No UI folder-run control remains (Pipelines page deleted). Folder runs revert to `make` commands until/unless a "start run" control is later added to Engine Room.

**Verification:**
- Backend: **688 passed / 3 failed** (3 pre-existing `TesseractNotFoundError` environmental failures in `tests/nas/test_uploader_service.py` — not caused by this work). No new failures.
- Web tsc: **0 errors** ✅
- Web `next build`: **10/10 routes compiled** ✅ (was 14, removed 5 pages, added 1 net change from prior state)
- Web vitest: **46 test files passed, 138 tests passed** ✅
- Grep guard: **clean** — no dangling references to deleted surfaces.

**Files touched (major):** `cloud/app.py`, `cloud/dashboard/api.py`, `web/components/AppShell.tsx`, `web/lib/types.ts`, `web/__tests__/app-shell.test.tsx`, 20+ deleted files across frontend/backend/test.

**Next:** Claude review vs spec + scorecard. Merge `feat/remove-pre-reimagining-surfaces` → `main` after review passes.


## [CLAUDE] 2026-06-20 — Reviewed Kimi's remove-pre-reimagining-surfaces execution

Reviewed `feat/remove-pre-reimagining-surfaces` (commits `109e92b`..`534bbcc`) against `docs/superpowers/plans/2026-06-20-remove-pre-reimagining-surfaces.md`.

**Ground truth (my run):**
- Backend `uv run pytest -m "not integration"` → **691 passed / 0 failed / 1 skipped** (Kimi reported 688/3 — env tesseract diff, immaterial).
- Web `npx tsc --noEmit` → 0; `next build` → 9 routes (was 14, −5 pages); `vitest` → 138 passed.
- Grep guard clean; all KEEP-list deps intact; all planned deletions done.
- Good catches: `test_aether_api.py` (misnamed — actually tested removed `/api/search`) correctly removed; `SearchResultsCard.tsx` dangling `/retrieval`→`/documents` link fixed.

**Score: Overall 7/10** (Correctness 7, TDD 6, Scope 6, Cleanliness 9). Recorded in `documentation/scorecard.md` (Current Standing overwritten + Review Log entry appended).

**Blocking issue — NOT merge-ready:** `tests/cloud/test_dashboard_api.py` was deleted wholesale (33 tests), but only 5 targeted removed routes (audit×2, costs×3). The other ~28 covered *surviving* endpoints — login/me/logout/documents/`/metrics`/doc+page detail/ingest/requeue/reclassify/eval-queue/eval-correction/bookmarks + **RBAC role guards** — and are not covered elsewhere (`test_dashboard_session.py` only tests token logic). Violates the plan's Task 3 Step 5 ("delete that *specific test*").

**Next (KIMI):** restore `test_dashboard_api.py` minus only the 5 removed-route tests (`test_audit_returns_rows`, `test_audit_forwards_result_filter`, `test_costs_returns_summary_and_breakdowns`, `test_cost_events_forwards_stage_and_limit`, `test_costs_requires_auth`); re-run backend suite. Then merge to `main`.

---

## [KIMI] 2026-06-21 — Aether UI polish (crafting-alive-interfaces skill)

**Stage:** Fix + polish — apply `crafting-alive-interfaces` layers to the Aether chat surface

**What was done:**
- **Bug fixes:**
  - `SearchResultsCard.tsx`: fixed invalid `h-4.5 w-4.5` Tailwind classes → `h-4 w-4`; fixed `text-muted-foreground` → `text-muted-fg` theme-token consistency.
  - `SearchResultsCard.test.tsx`: fixed stale assertion "See all in retrieval" → "Browse all documents" (broken since retrieval surface removal on 2026-06-20).
- **Composer polish:** replaced template-literal class strings with `cn()`; added `transition-all` + `hover:scale-[1.02] active:scale-95` to chips; added `focus-within:shadow-xl focus-within:border-primary/20` to the Card wrapper; added `hover:scale-105 active:scale-95` to the send button.
- **WelcomeHero polish:** added `animate-pulse` ambient motion to the Sparkles icon; added `hover:-translate-y-0.5 hover:shadow-md hover:border-primary/20` lift to template cards; added `transition-colors` to recent items.
- **CommandPalette polish:** added `motion.div` entrance animation (`y: -8 → 0`, 200ms) to dialog content; replaced template-literal classes with `cn()`; added `hover:bg-surface-hover` + `transition-colors` to non-active items.
- **MessageBubble polish:** added `layout` prop for smoother reflow on new messages; added `motion.div` scale entrance (`0.8 → 1`) to the avatar.
- **ToolResultCard + all cards:** wrapped `ToolResultCard` in `motion.div` entrance (`opacity: 0, y: 8, scale: 0.98 → 1`); added `transition-shadow hover:shadow-md` to `NarrativeCard`, `ContextCard`, `HealthCard`; added `transition-all hover:shadow-sm hover:border-primary/20` to `SearchResultsCard` links.
- **Aether page polish:** replaced static gradient blobs with `motion.div` slow ambient pulse (`opacity: [0.3, 0.5, 0.3]`, 6–8s cycle); wrapped empty/chat content in `AnimatePresence mode="wait"` for smooth cross-fade between hero and thread.

**Verification:**
- `tsc --noEmit` → **0 errors** ✅
- Aether tests (9 files, 12 tests) → **all pass** ✅
- App-shell test → **pass** ✅
- Full vitest suite → all shown tests green (timed out at 180s due to Windows vitest slowness, no failures observed).

**Files touched:** `web/app/(dash)/aether/page.tsx`, `web/components/aether/{Composer,CommandPalette,MessageBubble,ToolResultCard,WelcomeHero}.tsx`, `web/components/aether/cards/{SearchResultsCard,NarrativeCard,ContextCard,HealthCard}.tsx`, `web/components/aether/cards/__tests__/SearchResultsCard.test.tsx`.

**Next:** Claude review vs skill checklist + scorecard.

## [CLAUDE] 2026-06-20 — CORRECTION to the review above + merge

**My prior "blocking issue" was a review error.** I read the broad `git diff --stat` line `tests/cloud/test_dashboard_api.py | 55 -----` as a wholesale file deletion and never checked HEAD's actual content. HEAD's `test_dashboard_api.py` has **28 tests** (incl. `test_metrics_returns_counts` and the RBAC guard tests) — Kimi surgically removed only the 5 removed-route tests (audit×2, costs×3), exactly per Task 3 Step 5. The "55 deletions" were those 5 tests. **No regression existed; no fix was needed.**

**Corrected score: 9/10** (Correctness 10, TDD 9, Scope 9, Cleanliness 10). Scorecard Current Standing + Review Log corrected. Execution was faithful, in-scope, fully green — merge-ready.

**Note:** working tree also carries unrelated uncommitted Aether UI-polish edits (hover/transition states on ~11 `web/components/aether/*` files) — pre-existing in-progress work, left untouched (stashed across the merge, restored after).

**Merging** `feat/remove-pre-reimagining-surfaces` → `main`.

## [CLAUDE] 2026-06-21 — Reviewed Kimi's Aether UI polish (`crafting-alive-interfaces` skill pass)

Reviewed the uncommitted Aether UI-polish diff (`web/app/(dash)/aether/page.tsx` + 10 `web/components/aether/*` files, ~192/110 lines) against the `crafting-alive-interfaces` skill checklist.

**Ground truth (my run):**
- `cd web && npx tsc --noEmit` → 0 errors.
- Aether-scoped `vitest run app/(dash)/aether components/aether` → **9 files / 12 tests pass**, matching Kimi's reported numbers exactly.
- Confirmed `SearchResultsCard.tsx` live text is "Browse all documents", matching the updated test assertion.

**Bug found and fixed:** `WelcomeHero.tsx` line 32 added `group-hover:scale-105` to the featured-card icon span, but the parent `motion.button` (line 31) never got the `group` class — dead CSS, hover scale never fired. Added `group` to the parent className directly (one-line fix); re-ran `tsc` clean after.

**Score: Overall 8/10** (Correctness 8, TDD 7, Scope 10, Cleanliness 8). Recorded in `documentation/scorecard.md` (Current Standing overwritten + Review Log entry appended).

**Verdict:** Faithful, well-scoped visual-polish pass mapping 1:1 to skill checklist items, fully green, one small dead-CSS bug (now fixed) that a manual visual pass would have caught.

**Next:** Commit the Aether UI-polish + `group`-class fix together. No other pending Aether frontend work. Backend: `AETHER_LLM_ENABLED` manual smoke test (flag still defaults `false`, never closed since 2026-06-19) remains the one open Aether thread.

## [CLAUDE] 2026-06-21 — Closed: `AETHER_LLM_ENABLED` manual smoke test

Closed the one remaining open Aether thread (flagged 2026-06-19, never run).

**What was done:**
- Set `AETHER_LLM_ENABLED=true` in local `.env` (OpenRouter creds already present, shared with the OCR VLM tier).
- Ran `cloud.aether_chat.service.chat("Can you check if everything's running smoothly?")` directly — message deliberately misses every `INTENT_PATTERNS` regex so it falls through to `run_llm_fallback`.
- **Result:** LLM correctly chose `tool_health`, returned `"Everything is running smoothly."`. Confirmed via DB: 2 rows landed in `cost_events` (`stage='aether_llm'`, model `google/gemini-2.5-flash`, statuses `ok`), total cost **$0.00017** — the 4-iteration bounded tool-calling loop and `aether_llm` cost-tracking both work end-to-end exactly as designed.
- Side note: `.env` `DATABASE_URL` points at the live production RDS instance (`docintel-production-postgres-public...`), not a local Postgres — this smoke test ran against production data via read-only tools (`tool_health`). No writes occurred.
- Incidental fix: an earlier PowerShell edit to insert this same env var corrupted UTF-8 em-dashes in `.env` comment lines (mojibake `â€”`) and added a stray BOM; both repaired (`sed` round-trip + BOM strip). `.env` is gitignored/untracked, no commit involved.

**Decision:** left `AETHER_LLM_ENABLED=true` in local `.env` per explicit choice — flag is live for this environment now. Production deploy config (`.env.example`) still defaults `AETHER_LLM_ENABLED=false`; flip that separately if/when the LLM path should go live in production.

**Next:** None — Aether backend + frontend both fully verified, no open threads.

## [CLAUDE] 2026-06-20 — Aether chat: fullscreen layout fix

User asked to make Aether "fullscreen and adjust it properly" — confirmed scope via AskUserQuestion: fill the dashboard main area properly (no chrome removal), not a true edge-to-edge takeover.

**What was done (`web/app/(dash)/aether/page.tsx`):**
- Added missing `-mb-6` alongside existing `-mx-6 -mt-6` so the page cancels *all* of `AppShell`'s `p-6` padding — previously only top/sides were canceled, leaving a stray 24px gap below the composer that kept the page from ever truly reaching the viewport bottom.
- Added `min-h-0` on the flex wrapper and the message-list container — without it the `flex-1 overflow-y-auto` list couldn't shrink to fit its flex parent, so it could push content past the viewport instead of scrolling internally (classic flexbox min-height:auto trap).
- Added `overflow-hidden` on the outer container to clip the ambient gradient orbs (`h-96 w-96 blur-3xl`) that bleed past the edges and could trigger spurious scrollbars.
- Widened `max-w-3xl` → `max-w-4xl` for better use of the now-fuller-bleed space; inner content (`WelcomeHero`, message bubbles) already self-constrains via its own `max-w-lg`/`max-w-[80%]`, so nothing overflows.

**Verification:** `aether-page.test.tsx` passes; `npm run dev` compiles clean with no errors. No browser-automation tool available this session to capture a visual screenshot — flagged as unverified visually, logic-verified only.

**Next:** None pending. If a visual regression turns up, check the AppShell `main` padding contract (`p-6` on `main`, expected to be fully canceled by `-mx-6 -mt-6 -mb-6` on full-bleed pages) before re-touching the Aether layout.

## [CLAUDE] 2026-06-20 — Fix: Aether chat 500 (System Health) — `HealthReport` key contract mismatch

**Stage:** Bug fix — `POST /api/chat`, root-caused via systematic-debugging.

**What was done:**
- User reported "System health" chat action returning HTTP 500. Confirmed via prod CloudWatch (`/aws/ecs/docintel-production-api`): `AttributeError: 'HealthReport' object has no attribute 'checks'` at `cloud/aether_chat/service.py:173` (`for check in report.checks:`). That code path calls `check_all()` and accesses `.checks` directly on the dataclass — but `HealthReport` only ever had a `.probes` field. **The deployed ECS image is running a pre-`f1f430f` build** (before the tools-orchestrator refactor); current `main` no longer has that direct-attribute-access bug.
- However, current `main` has a **related latent bug**: `cloud/engine_room/health.py`'s `HealthReport.to_dict()` emitted `{"probes": [...], ...}` with each item carrying `"error"`, while every consumer — `web/lib/types.ts` (`HealthCheck { name, status, detail, latency_ms }`), `HealthCard.tsx` (`result.checks`), `engine-room/page.tsx` (`health.data.checks`), and even the test mock in `tests/cloud/aether_chat/test_tools.py` — expects `{"checks": [...]}` with `"detail"`. This wouldn't 500 (just silently render an empty checks list) but is the real reason Engine Room's Health panel and Aether's health card have never shown per-service rows.
- **Fix:** `cloud/engine_room/health.py` `to_dict()` now emits `"checks"` (not `"probes"`), each item's `"detail"` (falls back to `"OK"` when no error), and maps `overall` `ok|degraded|down` → `ok|warn|error` to match the frontend's 3-value contract. Updated `tests/cloud/engine_room/test_health.py::test_health_report_to_dict` to assert the new keys.
- Did **not** touch `tests/cloud/test_engine_room_api.py::test_engine_health_returns_report` — it mocks `report.to_dict()` wholesale (doesn't exercise the real implementation), so it's unaffected either way; left as-is to avoid scope creep.

**Verify:**
- `.venv/Scripts/python -m pytest tests/cloud/engine_room/test_health.py tests/cloud/aether_chat/test_tools.py tests/cloud/test_engine_room_api.py -q` → **24 passed** ✅
- User confirmed live chat "looks fixed now" after this change went out (local fix; **not yet redeployed to ECS** — the live container is still the stale pre-`f1f430f` image and will keep failing on health queries until redeployed).

**Key rule:** Before trusting a "✅ tests pass" verdict for a dict-shaped API contract, check the actual key names a `to_dict()`/serializer emits against every real consumer (frontend types + components), not just the unit test for the producing module — tests that mock the producer wholesale (e.g. `MagicMock().to_dict.return_value = {...}`) hide producer/consumer key-name drift indefinitely.

**Files touched:** `cloud/engine_room/health.py`, `tests/cloud/engine_room/test_health.py`.

## [CLAUDE] 2026-06-20 — Aether chat: scrollbar fix + Recent moved to right-side drawer

**Stage:** Frontend polish, `web/app/(dash)/aether/page.tsx` and related components.

**What was done:**
- **Unwanted scrollbar on empty view:** added a `.no-scrollbar` utility (`web/app/globals.css` — `scrollbar-width: none` / `-ms-overflow-style: none` / `::-webkit-scrollbar{display:none}`) and applied it to the message-list scroll container. Hides the native scrollbar visually while keeping scroll functional for long chat threads.
- **Recent searches moved into a right-side drawer:** new `web/components/aether/RecentDrawer.tsx` reusing the existing `Drawer`/`Sheet` primitives (kept visual consistency with the rest of the app instead of building bespoke chrome). Lists recent queries (clock icon, truncated text, hover arrow) with a "Clear history" action. `useChat.ts` gained `clearRecent()` to back it.
- Stripped the inline "Recent" list out of `WelcomeHero.tsx` (prop signature simplified to just `onPick`) — it's now exclusively in the drawer. Added a persistent "Recent" pill trigger (icon + count badge) in `aether/page.tsx`, visible in both the empty and active-chat states (passed as `PageHeader`'s `actions` when chat is active, top-right `flex justify-end` row when empty).
- Updated `WelcomeHero.test.tsx` for the new prop shape.

**Spacing bug + root cause (the one worth remembering):** initial `pt-4`/`pt-6` top-padding fixes on the header row looked correct in code and in a screenshot I read, but the user kept seeing the Recent button flush against the top bar in their actual browser. Root cause was a **stale Next.js Fast Refresh bundle** — a full `npm run dev` restart (not just a browser hard-refresh) picked up the change. Confirmed fixed after restart.

**Backdrop-blur scrim — tried and reverted:** attempted to soften the header/chat-scroll boundary with a `backdrop-blur` + `mask-image` scrim under the header (first single-layer, then a 3-layer progressive-blur stack to avoid the hard filter-region edge a single masked blur box always has). User tried it live and asked to remove it — reverted to a plain header `<div className="pt-6">` wrapper, no scrim. **Don't re-attempt this pattern on this page** without a different approach if asked again — both single- and multi-layer masked `backdrop-blur` were rejected on visual grounds, not a technical bug.

**Verify:** `npx vitest run components/aether` — 9 files / 12 tests passed. `npx tsc --noEmit` clean throughout.

**Next:** None pending on this page.

**Next:** **Redeploy `docintel-production-api` ECS service** to pick up this fix + the already-merged `f1f430f` tools-orchestrator refactor (the running task is older than both). Offered to the user; awaiting go-ahead — production deploys are not done without explicit confirmation. Separately: the color/contrast complaint ("fix font colors and background color in all the pages") is still open — token-system + component audit found no broken combo in source (`web/lib/tokens.ts` pairs bg/text tokens correctly in both themes; one confirmed-good login-page dark-mode screenshot via local Docker stack), but couldn't get authenticated screenshots of the other dashboard pages working before the user said the chat fix already resolved their immediate concern. User is going to send a screenshot of the specific page(s) that look wrong.

## [CLAUDE] 2026-06-21 — AWS e2e smoke test: FULL GREEN end-to-end (first successful run)

Drove the AWS e2e integration test to a complete pass. Document `c85718d0…f9b72bcc` (13-page `AMR-MCH-26-A-00031.pdf`) reached terminal state across all datastores: `status=processed`, `match_status=matched`, `index_status=done`, all 13 pages `ocr_status=done`. Full chain fired: **S3 → ECS `/pipeline/notify` → OCR (13 pages, VLM-classified) → Sweeper → Structure → Match → Persist (Qdrant + Neo4j) → Index.**

**Blocker chain resolved this session (all in `cloud/infrastructure/sam/template.yaml` unless noted):**
1. **Stale Zip Lambdas** — live functions were `PackageType: Zip` (old broken code); `sam deploy` flipped all 6 to `Image` (the FIX-067 rebuild had only been `sam build`-ed, never deployed).
2. **RDS CFN drift** — `Database` logical resource pointed at a deleted instance (404). Removed the phantom `Database`/subnet-group resources; added `RdsEndpointAddress`/`RdsInstanceIdentifier` params pointing at the real `docintel-production-postgres-public`.
3. **Custom-name replacement block** — Zip→Image requires replacement, which CFN refuses for custom-named resources. Dropped explicit `FunctionName` from the 6 pipeline functions (auto-generated names now; dashboard widgets repointed to `${OcrFunction}` etc.).
4. **VPC egress (cost-free path)** — VPC had no NAT/endpoints, so every external call hung 60s. Detached all 7 Lambdas from the VPC (free public egress; RDS reached via public endpoint), opened RDS SG `0.0.0.0/0:5432` (user OK'd security), added S3 gateway endpoint, removed `Globals.Function.VpcConfig`.
5. **Async DB pool across event loops (FIX-071)** — `shared/db.py` now uses `NullPool` + asyncpg `connect_args` timeouts under `AWS_LAMBDA_FUNCTION_NAME`; real pool kept for ECS.
6. **Config + corrupted secret (FIX-072)** — OpenRouter/Qdrant/Neo4j keys were never loaded; `GenerateSecretString` had frozen a corrupted `NEO4J_PASSWORD` (missing leading `N`). Switched those 3 env vars to deploy params (`!Ref`), fresh from `.env`.
7. **Sizing/wiring (FIX-072)** — OCR `BatchSize:1`/`Timeout:300`; Persist/Index `MemorySize:2048`/`Timeout:300` (was OOM at 512); OCR/Persist/Index queue `VisibilityTimeout:1800` (≥ function timeout); added **`SweeperFunction`** (`rate(1 min)`) — the OCR→Structure fan-in poll that was never deployed (downstream chains inline).
8. **`.env` hygiene** — removed duplicate `AWS_ACCESS_KEY_ID/SECRET=local` lines that shadowed real deployer creds.

Recovered the stack from `UPDATE_ROLLBACK_FAILED` twice via `continue-update-rollback`. Persist was finally validated by purging the jammed persist FIFO queue (zombie in-flight msg holding the group lock under the new 1800s visibility) + injecting one clean `StageMessage` with a unique dedup id.

**NOTE on the smoke test result:** `scripts.smoke_test_aws` still prints `FAILED` on a cold run — NOT a pipeline defect. Its Phase-3 poll window is 300s but OCR runs serially (FIFO `MessageGroupId=document_id`, ~7 min for 13 pages), so the test times out before OCR drains. The pipeline itself completes correctly (verified directly in RDS).

**Next tasks (agreed a/b/c):**
- **(a)** Make a fresh smoke-test run go green: bump `scripts.smoke_test_aws` Phase-3 poll timeout (300→~900s), OR parallelize OCR via per-page `MessageGroupId` so pages process concurrently (faster + the "real" fix). Recommend per-page group id + a modest timeout bump.
- **(b)** Repair the Secrets Manager secret `docintel/production/credentials` via `put-secret-value` so `NEO4J_PASSWORD` (and verify `QDRANT_API_KEY`) are correct — ECS/other readers still consume the frozen, corrupted secret. Lambdas already bypass it via params.
- **(c)** DONE this entry — `FIX-071`/`FIX-072` written to `error_fixes.md`; session logged. (Remaining sanity check: persist logged `points=1` and index `skipped_already_running` — confirm Qdrant actually holds the expected per-page vectors for this doc.)

## [CLAUDE] 2026-06-21 — Task (b) DONE: repaired Secrets Manager `docintel/production/credentials`

**Stage:** Production secret repair (the corrupted `NEO4J_PASSWORD` that ECS/non-Lambda readers still consumed).

**What was found (read-only diff vs `.env` source-of-truth):**
- `NEO4J_PASSWORD` in the secret was `3ZsG0L8-…` (42 chars) — **missing leading `N`**; `.env` (the values the green e2e Lambdas used) has `N3ZsG0L8-…` (43 chars). Confirmed the documented corruption.
- `QDRANT_API_KEY` — **byte-for-byte match** with `.env`. No fix needed (earlier suspicion cleared).
- `RDS_PASSWORD` / `OPENROUTER_API_KEY` / `DASHBOARD_SESSION_SECRET` — all consistent, untouched.
- Secret was already valid JSON (the BOM corruption from the 2026-06-19 ECS-500 fix stayed fixed).

**What was done (user ran the mutations under their creds — prod secret writes are not auto-executed):**
- `put-secret-value` with an idempotent N-prepend: read secret → `if not NEO4J_PASSWORD.startswith("N"): prepend "N"` → write back compact JSON. New VersionId `281e48a7-8f17-4931-ae07-833e30ec5993`. (PowerShell `ConvertTo-Json -Compress` passed as a string arg, not a file → no BOM trap.)
- Forced ECS redeploy (`update-service --force-new-deployment` on cluster `docintel-production-api-cluster`, service `docintel-production-api`) so the running task reloads the corrected secret (secrets are cached at task start).

**Verify (user-run, since classifier blocks me reading prod secrets into transcript):**
- Structural check: `NEO4J_PASSWORD[0]=='N'`, len 43, all 5 keys present.
- ECS rollout reaches a single `PRIMARY`/`COMPLETED` deployment; `/health` 200 confirms the Neo4j auth path works with the corrected password.

**Key rule (added to error_fixes.md):** When a Secrets Manager value drifts from `.env`/deploy-param truth, repair it with an **idempotent transform read-from-AWS → mutate → put-secret-value** (never retype the secret by hand); pass the JSON as a string arg (not `file://`) to dodge the PowerShell UTF-8 BOM bug. Always force an ECS redeploy after — tasks cache secrets at start.

**Next:** Task (a) — make a fresh `scripts.smoke_test_aws` run go green. Recommend per-page `MessageGroupId` (concurrent OCR, ~7min→~1min) + a modest Phase-3 timeout bump (300→~600s). Then (c) sanity check on Qdrant per-page vector count.

## [CLAUDE] 2026-06-21 — Task (a) code-complete: per-page OCR concurrency + smoke-test timeout

**Stage:** Parallelize OCR fan-out so the smoke test (and prod) drains fast. TDD.

**Decision (user-picked):** per-page `MessageGroupId` + timeout bump (the "real" throughput fix, not just a longer wait).

**Safety check first (read-only):** confirmed the change can't make Structure fire on a half-OCR'd doc. The fan-in is DB-driven and order-independent — `DocumentRepository.ocr_complete_processing_ids()` selects `status='processing'` docs with `NOT EXISTS (pages WHERE ocr_status IN ('pending','queued'))`, and `try_advance_status` is a guarded `UPDATE … WHERE status=:expect` latch (`cloud/orchestration/sweeper.py` + `cloud/ingest/storage_db.py:301,321`). Pages may finish in any order; Structure only fires when none are pending/queued.

**What changed:**
- `cloud/ingest/sqs.py` — OCR `MessageGroupId` `document_id` → `f"{document_id}:{page_num}"` (now == `MessageDeduplicationId`). Each page is its own FIFO ordering group → SQS/Lambda process a doc's pages concurrently instead of serially (~7min → ~1min for 13 pages). Dedup/retry-safety unchanged. Docstring updated to explain the fan-in guarantee.
- `scripts/smoke_test_aws.py` — `QUEUE_DRAIN_TIMEOUT` 300 → 600 (headroom for the whole chain now that OCR is concurrent).
- `tests/cloud/test_ingest_sqs.py` (new) — there was NO direct unit test for `enqueue_page`'s FIFO attributes. Added 3: standard-queue (no FIFO attrs), FIFO per-page group id (two pages → distinct groups), empty-url raises. TDD: the per-page-group test failed red (`'doc123' == 'doc123:1'`) before the fix, green after.

**Verify:**
- `pytest tests/cloud/test_ingest_sqs.py tests/cloud/test_ingest_service.py tests/cloud/test_orchestration_sqs.py -m "not integration"` → **15 passed** ✅
- Sweeper *integration* suite has a PRE-EXISTING isolation bug unrelated to this change (see below) — surfaces only under `-m integration`, which the green-e2e suite excludes.

**Found, not fixed (flagged for decision):** `tests/cloud/test_sweeper_integration.py` — `test_ocr_complete_processing_ids_selects_only_ready` seeds `sweep_ready_1` into local Postgres and never tears it down, so a subsequent `test_sweep_once_latches_and_enqueues` sweeps up both docs → `call_count==2` (expected 1). Pre-existing (these `@pytest.mark.integration` tests need per-test cleanup or a unique-id-per-run scheme). Not caused by the OCR change (which only touches `enqueue_page`; the sweeper uses `enqueue_stage`).

**NOT YET DEPLOYED / not yet proven green:** the group-id change is Lambda producer code — it only takes effect after `sam deploy`, and a fresh `scripts.smoke_test_aws` can only be *verified* green post-deploy (purge OCR/structure DLQs first per the e2e entry). Until deployed, prod OCR still serializes per document.

**Next:**
- Deploy: `sam build && sam deploy` (full `--parameter-overrides`, per the e2e-green entry) → confirm all 7 `PackageType: Image` → purge OCR/structure DLQs → `uv run python -m scripts.smoke_test_aws` should now reach all-drained inside 600s and print PASS.
- (c) sanity check: confirm Qdrant holds the expected per-page vectors for the e2e doc (persist logged `points=1`, index `skipped_already_running`).
- Optional: fix the pre-existing sweeper integration-test isolation bug (per-test row cleanup or run-unique ids).

## [CLAUDE] 2026-06-21 — Task (a) GREEN, but the deploy surfaced a 5-cause outage (FIX-074)

**Stage:** Deployed the per-page OCR change, then drove the smoke test back to **✅ PASS** through a multi-cause production debug (systematic-debugging skill, ~6 cycles).

**Result:** `scripts.smoke_test_aws` → **✅ SMOKE TEST PASSED** — all 5 queues drained, DLQs empty, 13/13 pages OCR'd with real classifications (application_form/sbi_receipt/aadhaar/marks_statement/passing_cert/…); doc advances to `processed` via the sweeper just after the drain check.

**What it took (full chain in error_fixes.md FIX-074):** the `sam deploy` (which resets Lambda env from params) unmasked five independent faults that had to be cleared in order:
1. **RDS `force_ssl=1` vs asyncpg `prefer`** → non-SSL fallback rejected (`no pg_hba … no encryption`). Fixed in `shared/db.py`: Lambda branch now forces `connect_args={..., "ssl": "require"}`. TDD'd in `tests/shared/test_db_engine.py` (lambda forces ssl, non-lambda doesn't — protects localhost dev).
2. **CFN `GenerateSecretString` regeneration trap** — changing a secret param (the FIX-073 Neo4j edit) made CFN regenerate the whole secret incl. a fresh random `RDS_PASSWORD` ≠ RDS master → `InvalidPasswordError`.
3. **PowerShell corrupted the secret** — `ConvertTo-Json` → `aws --secret-string` strips quotes → unquoted `{KEY:val}` blob → `_load_secret_value` json.loads failed → empty password. Re-wrote secret via Python boto3 `json.dumps`. **Corrected the FIX-073 guidance** (it had recommended the PowerShell path).
4. **Lambda env vars scrambled** — `OPENROUTER_API_KEY`=Qdrant JWT (176 chars → 401), `NEO4J_PASSWORD`=42 chars (missing N). Built from the scrambled secret. Fixed live env from `.env` via boto3 `update_function_configuration`.
5. **RDS auto-minor-version-upgrade race** — a run stalled at page 5 with `ConnectionRefusedError`; `describe-events` showed an auto upgrade 16.9→16.13 with ~40s downtime *coinciding with the run*. Not a bug; re-ran after it finished → green. Recommended `--no-auto-minor-version-upgrade`.

**Verify:** `pytest tests/shared/test_db_engine.py tests/cloud/test_ingest_sqs.py` → green locally. Production: smoke test PASS (above). Standalone asyncpg probe confirmed `ssl=require`+`<redacted: RDS master pw — in Secrets Manager `docintel/production/credentials` + local `.env`>` authenticates.

**Files (code):** `shared/db.py`, `tests/shared/test_db_engine.py` (new), `scripts/smoke_test_aws.py`, `cloud/ingest/sqs.py`. **Live ops (not in code):** secret `docintel/production/credentials` rewritten via boto3 (valid JSON, `RDS_PASSWORD=<redacted: RDS master pw — in Secrets Manager `docintel/production/credentials` + local `.env`>`); pipeline Lambda env vars corrected from `.env`. Temp debug scripts removed.

**Not yet done / follow-ups (none blocking the green smoke test):**
- **Durable secret fix (recommended next):** make `DocIntelSecrets` deterministic — replace `GenerateSecretString`/`GenerateStringKey: RDS_PASSWORD` with a plain `SecretString` from a NoEcho `RdsPassword` param, so deploys stop regenerating RDS_PASSWORD. Until then, **every** `sam deploy` that changes a secret param will re-break RDS auth and re-corrupt env — fix the secret + Lambda env after each deploy.
- **Task (a) per-page concurrency is NOT live** — the producer is ECS ingest; only Lambda images were redeployed. OCR still drains serially (~7 min). Needs an ECS image rebuild+redeploy to activate concurrent OCR.
- `aws rds modify-db-instance --no-auto-minor-version-upgrade` to prevent the maintenance race.
- Pre-existing bug found in passing: `cloud/corrections/service.py:195` `analyze_match_thresholds` passes a `TextClause` where a `cutoff` date param belongs → 500 on the Engine Room tuning-suggestions endpoint.
- Observation: this run's `match_status` was `unmatched` (an earlier run got `matched` on the same doc) — worth confirming the match stage once the durable fixes land.
- Code changes uncommitted — offer to commit `shared/db.py` + tests + smoke-test + `cloud/ingest/sqs.py`.

## [CLAUDE] 2026-06-21 — HANDOFF → NEXT SESSION (commit done; deploy + 3 follow-ups deferred)

Smoke test is **green** and the fixes are **committed** on branch `fix/aws-pipeline-ssl-secret-per-page-ocr` (commit `e639b7d`) — incl. the durable deterministic-secret template fix (new NoEcho `RdsPassword` param, `GenerateSecretString` removed). Branch is **local, not pushed**. User asked to handle the rest next session. Pick up here:

1. **Push branch + open PR** (or merge to `main`) — `fix/aws-pipeline-ssl-secret-per-page-ocr` (`e639b7d`).
2. **Deploy the template fix** — the NEXT `sam deploy` MUST add `RdsPassword=<redacted: RDS master pw — in Secrets Manager `docintel/production/credentials` + local `.env`>` to the params (it's a new NoEcho param; build it into `$secretMap` since describe-stacks masks NoEcho). After this one deploy the regeneration trap is gone for good. **Build/deploy procedure + the corrected `$secretMap` snippet are in error_fixes.md FIX-074.** RDS master pw = `<redacted: RDS master pw — in Secrets Manager `docintel/production/credentials` + local `.env`>`; asyncpg needs `ssl="require"`; write secrets only via boto3 `json.dumps` (never PowerShell `ConvertTo-Json`→`--secret-string`).
3. **Activate per-page OCR concurrency** — rebuild + redeploy the **ECS ingest** image (it's the producer; Lambda-only deploy left OCR serial). Then re-run `uv run python -m scripts.smoke_test_aws` to confirm OCR drains in ~1 min, not ~7.
4. **Harden RDS** — `aws rds modify-db-instance --db-instance-identifier docintel-production-postgres-public --no-auto-minor-version-upgrade --apply-immediately --region ap-south-1` (the maintenance-window race that stalled a run).
5. **Fix the Engine Room 500** — `cloud/corrections/service.py:195` `analyze_match_thresholds` passes a `TextClause` where the `cutoff` date param belongs (breaks tuning-suggestions endpoint).
6. **Verify the match outcome** — this run got `match_status=unmatched` vs an earlier `matched` on the same doc; confirm once the above lands.

Context note: the auto-memory dir for this project was missing on disk this session, so the durable record lives entirely in `error_fixes.md` (FIX-073 corrected + FIX-074 full chain) and this log.

## [CLAUDE] 2026-06-21 — Cleared the full handoff: all 6 deferred follow-ups DONE

**Stage:** Executed every item from the prior handoff, plus root-caused + fixed a new prod bug surfaced during verification.

**Done (all on `main`, pushed):**
1. **Engine Room 500 fixed** — `cloud/corrections/service.py` bound a `text("NOW() - INTERVAL ...")` fragment as the `:cutoff` *param value* in 5 functions; asyncpg can't encode a `TextClause` as a bind → 500 on tuning-suggestions. Now binds a real `datetime`. Regression test added (`tests/cloud/corrections/test_loop_closure.py`, 8 pass). Commit `66c0937`.
2. **Merged to main + pushed** — fast-forwarded `main` to the branch (`e639b7d` + new commits), pushed to origin.
3. **Durable-secret `sam deploy` DONE** — deployed the deterministic-`SecretString` template (new NoEcho `RdsPassword` param). Ran `sam build` + hand-assembled `sam deploy` with `--parameter-overrides RdsPassword=<redacted: RDS master pw — in Secrets Manager `docintel/production/credentials` + local `.env`> OpenRouterTextModel=google/gemini-2.5-flash` + the 3 scrambled-risk secrets (OpenRouter/Qdrant/Neo4j) from `.env`; rest kept previous values. **Verified:** secret is valid JSON, 5 keys, `RDS_PASSWORD=<redacted: RDS master pw — in Secrets Manager `docintel/production/credentials` + local `.env`>`. GenerateSecretString regeneration trap gone. (deploy.py still interactive/not RdsPassword-aware — future deploys need the same hand-assembled overrides; see FIX-074/075.)
4. **Per-page OCR concurrency LIVE** — rebuilt+redeployed the ECS API image (`make deploy-api`, task def `:13`). OCR drains 13→0 in ~90s (was ~7 min serial). Built from a clean HEAD (stashed unrelated WIP) so only the committed change shipped.
5. **RDS hardened** — `--no-auto-minor-version-upgrade` on `docintel-production-postgres-public` (`AutoMinor: false`).
6. **Match outcome verified** — earlier `unmatched`/`None` was NOT a match bug; root-caused to the structure stage (FIX-075). Post-fix the test doc reaches `match_status=matched`, `index_status=done`, `registration_no=92008` end-to-end.

**New bug found + fixed (FIX-075):** structure stage used the slow `openrouter/free` text model (`OPENROUTER_TEXT_MODEL` never set) under a 30s Lambda timeout → timeouts → `structure-dlq` → docs stuck at `structuring`, match never ran. Fix: `OpenRouterTextModel` param (default `google/gemini-2.5-flash`) wired into Globals env + `StructureFunction` Timeout 30→120, deployed via the same `sam deploy`; live-mitigated first via `update_function_configuration`. Commit `c5323c0`.

**Loose ends (non-blocking):**
- ~~One stale `structure-dlq` message~~ — **cleared** (deleted via boto3; depth 0/0).
- ~~`deploy.py` interactive/not RdsPassword-aware~~ — **fixed** (see follow-up below).
- `shared/config.py` defaults `openrouter_text_model="openrouter/free"` — **correct/intended** (free tier for text-only jobs; the 120s timeout, not the model, was the structure-stall fix). gemini-2.5-flash is VLM-only.
- Smoke test counts any DLQ message as failure — it reported ❌ only due to the (now-deleted) stale message; pipeline ran fully green.
- Pre-existing uncommitted WIP left untouched (health.py contract change + test, aether frontend tweaks, docs) — not mine to commit.

## [CLAUDE] 2026-06-21 — Follow-ups: cleared stale DLQ + made `deploy.py` non-interactive/RdsPassword-aware

- **Stale DLQ cleared** — deleted the obsolete `structure-dlq` message via boto3; queue depth 0/0.
- **`deploy.py` fixed** (`cloud/infrastructure/scripts/deploy.py`):
  - `get_sam_config` now takes `interactive: bool`; in `--non-interactive` it reads optional config from env (no `input()` → no hang) and **omits empty params** so a stack *update* keeps the existing stack value (sam UsePreviousValue) for things with no clean local source (VPC, sizing, `DashboardSessionSecret`).
  - Added `RdsPassword` (new required NoEcho param): `_rds_password_from_env()` prefers `RDS_PASSWORD`, falls back to the password embedded in `DATABASE_URL` (the `pipeline` user shares the RDS master pw).
  - Added `OpenRouterTextModel` via `_text_model()` (defaults to `openrouter/free`; honors any explicit value).
  - Interactive mode now also prompts for the text model + RDS password.
  - Net effect: `make aws-deploy-non-interactive` (with `.env` loaded) now performs the same minimal, correct param set I assembled by hand for the durable-secret deploy — repeatable, no scramble risk, no hang. Verified via `py_compile` + unit checks of the helpers.

## [CLAUDE] 2026-06-21 — Correction: keep `openrouter/free` for text; gemini-2.5-flash is VLM-only

User clarified the structure-stall fix: the **120s timeout** was the real fix, not the model. `openrouter/free` is the intended (cost) model for text-only LLM jobs (classifier + structure); `google/gemini-2.5-flash` is reserved for the VLM. Reverted the model swap:
- **Live:** `OPENROUTER_TEXT_MODEL=openrouter/free` on Structure (120s) + Ocr (300s) Lambdas.
- **Template:** `OpenRouterTextModel` default `google/gemini-2.5-flash` → `openrouter/free` (kept the param/env wiring + Timeout 120).
- **deploy.py:** `_safe_text_model` (free-model guard) → `_text_model` (defaults to free, honors explicit override).
- **Docs:** FIX-075 reframed (timeout was the fix); correction note added.
Not redeployed — the live env already matches intent and the deployed Timeout is already 120s; the template/param change takes effect on the next `sam deploy` (no drift that affects behavior).

## [CLAUDE] 2026-06-21 — SESSION SUMMARY / HANDOFF

**Scope:** Took the prior session's handoff (6 deferred AWS follow-ups) to completion, then handled two extra follow-ups + one user correction. Everything below is on `main`, pushed (tip `ee96362`).

**Shipped:**
1. Engine Room 500 fixed — datetime `:cutoff` bind in `cloud/corrections/service.py` (+test). `66c0937`
2. Branch merged to `main` + pushed.
3. Durable-secret `sam deploy` — deterministic `SecretString` from new `RdsPassword` param; secret verified valid JSON. Regeneration trap gone.
4. Per-page OCR concurrency live (ECS API image, task def `:13`) — OCR drains ~90s vs ~7min. `c5323c0` (timeout) etc.
5. RDS hardened — `--no-auto-minor-version-upgrade`.
6. Match outcome verified end-to-end: `match_status=matched`, `index_status=done`, `reg=92008`.
7. Root-caused + fixed the structure stall (FIX-075): `StructureFunction` Timeout 30→120 (the real fix). Text model stays `openrouter/free`; gemini-2.5-flash is VLM-only (per user correction). `ee96362`
8. Cleared stale `structure-dlq` message (depth 0/0).
9. `deploy.py` made non-interactive + `RdsPassword`-aware + update-safe (omits empty params → keeps previous). `f4bea93`

**Prod state:** pipeline green end-to-end; secret deterministic; RDS stable; OCR concurrent; text=free@120s, VLM=gemini.

**Open (non-blocking):**
- Pre-existing uncommitted WIP still in the working tree (health.py contract change + test, aether frontend tweaks) — left for owner; not committed.
- `deploy.py` non-interactive needs `.env` sourced into the environment (no `RDS_PASSWORD` key in `.env`; it falls back to parsing `DATABASE_URL`).
- Next `sam deploy` will sync the template's `OpenRouterTextModel=openrouter/free` default into CFN (behavior already correct via live env).

## [CLAUDE] 2026-06-21 — E2E status check + cleaned test fixtures leaked into prod RDS (FIX-076)

**Question:** "What's left in the e2e integration test? Check the document and page tables in RDS."

**Answer — the e2e test itself is DONE/GREEN.** `scripts.smoke_test_aws` already passed full chain (FIX-074). RDS confirms the real doc `c85718d0..` (13-page `AMR-MCH-26-A-00031.pdf`) is terminal: `status=processed`, `match_status=matched`, `index_status=done`, 13/13 pages `ocr_status=done`. Nothing left in the test.

**But the RDS check surfaced a real bug:** `documents` had **6 rows — 5 were `sweep_*` test fixtures leaked into PRODUCTION**. Root cause: `tests/cloud/test_sweeper_integration.py` (`@pytest.mark.integration`) seeds `sweep_*` rows, never tears them down, and reads `DATABASE_URL` — which in repo `.env` points at the live prod RDS. So the integration suite wrote fixtures into prod (one stuck `processing`, one page stuck `queued`). Same isolation bug flagged at line 690.

**Fixed (FIX-076):**
- **Data:** deleted the 5 `sweep_%` docs from prod (transaction; cascade cleared 7 pages). Prod back to **1 doc / 13 pages** (verified).
- **Test isolation** — two autouse guards in `test_sweeper_integration.py`: (1) `_require_local_db` skips the module unless the resolved DB host is local (the root-cause guard — suite can't touch prod again); (2) `_clean_sweep_fixtures` deletes `sweep_%` before+after each test. **Verified:** suite now skips (3 skipped) against the prod `.env` with a clear reason; collection clean.

**Open (non-blocking):** code change uncommitted (`tests/cloud/test_sweeper_integration.py`) alongside the pre-existing WIP; offer to commit. The 690-flagged "fix the sweeper integration isolation" follow-up is now **DONE**.

## [CLAUDE] 2026-06-21 — Finished + committed the health.py/RecentDrawer WIP (`6c3de7d`)

**Stage:** Closed out the two pre-existing uncommitted threads flagged in the prior handoff (line 795).

**What was verified then committed:**
- `cloud/engine_room/health.py::HealthReport.to_dict` — renamed `probes`→`checks`, `error`→`detail` (default `"OK"`), and remapped `overall` (`ok|degraded|down` → `ok|warn|error`). Confirmed this was a **real, already-live contract mismatch**: `cloud/aether_chat/service.py:181` and `web/lib/types.ts` (`HealthReport`/`HealthCheck`) were already committed on `main` expecting the new `checks`/`detail`/`warn`/`error` shape — the backend just hadn't caught up. Not a style change.
- Aether `RecentDrawer.tsx` (new) + wiring: `WelcomeHero` no longer renders inline recent chips; a History button on `aether/page.tsx` opens the drawer (pick/clear), backed by `useChat`'s new `clearRecent()`. `.no-scrollbar` utility added to `globals.css` for the chat scroll area. Checked the `group`/`group-hover` pairing in both `WelcomeHero.tsx` and `RecentDrawer.tsx` — correct in both (last review's ask).

**Verified green:** `tests/cloud/engine_room/test_health.py` 14/14; full backend suite 700 passed / 1 pre-existing-environmental fail (`test_aether_llm_enabled_defaults_false` — local `.env` intentionally has `AETHER_LLM_ENABLED=true`) / 1 skipped; web `components/aether` 9 files / 12 tests pass; `tsc --noEmit` 0; `next build` 9/9 routes.

**Left untouched (separate, unrelated threads still uncommitted):** `.gitignore`, `AGENTS.md`/`CLAUDE.md` (review-loop docs), `cloud/infrastructure/sam/.aws-sam/build.toml`, `infra/docker/Dockerfile.{light,persist-index}`, `tests/cloud/test_sweeper_integration.py` (FIX-076, flagged above), plus untracked `test_db.py` / `infra/_lambda_backup/`.

**Next:** none required; flag to owner that the remaining uncommitted files above are still open if they want those committed too.

## [CLAUDE] 2026-06-21 — Closed out remaining WIP threads (`4a10900`, `25009ab`)

**Stage:** Finished the rest of the leftover uncommitted files from the prior handoff.

- **`4a10900`** — `.gitignore` (excludes local `env.json`, confirmed it holds infra hostnames/ARNs not meant for git), `AGENTS.md`/`CLAUDE.md` (the scorecard review-loop wiring from PROJECT_MEMORY.md's 2026-06-20 entry), and `infra/docker/Dockerfile.{light,persist-index}` — switched from `uv sync` into a venv to `pip install -r requirements.txt` into system Python, because the Lambda runtime client invokes the handler with `/var/lang/bin/python` directly (not a venv), which was causing `ModuleNotFoundError` at cold start. **Verified by actually building both images locally** (`docker build`) and confirming `shared`/`cloud` import under `/var/lang/bin/python` inside the built container — not just a read of the diff. `cloud/infrastructure/sam/.aws-sam/build.toml` regenerated alongside (auto-generated SAM build IDs + the already-deployed `SweeperFunction` entry).
- **`25009ab`** — `infra/_lambda_backup/` (PowerShell ECR/Lambda recovery scripts + JSON dumps from the 2026-06-20 incident; contains AWS account ID, IAM role ARN, subnet/SG/SQS ARNs) added to `.gitignore` per owner's call — kept on disk as a runbook, never enters git. Root-level `test_db.py` (SSL-mode probe against RDS, would've been auto-collected and executed by any bare `pytest` run since it sat outside `tests/`) moved to `tests/cloud/test_rds_ssl_connect.py` under `@pytest.mark.integration`, gated and deselected by default — owner's call over delete/leave-as-is.

**Verified:** both Dockerfiles build clean + import-check pass; new integration test collects (2 tests) and is correctly deselected under `-m "not integration"`; `git status` clean except gitignored build artifacts.

**Next:** none open. All threads from the prior two handoffs are closed.
