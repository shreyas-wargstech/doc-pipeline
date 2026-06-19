
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

