# Spec: Next.js Dashboard Migration + UI Polish

- **Date:** 2026-06-08
- **Status:** Approved (brainstorm)
- **Supersedes UI of:** DASH-1 HTMX/Jinja dashboard (`cloud/dashboard/templates`, `static`, HTML `router.py`)
- **Related:** `docs/superpowers/specs/2026-06-06-pipeline-dashboard-dash1*`, auto-memory `dashboard-plan.md`

## 1. Motivation

The DASH-1 dashboard (FastAPI + HTMX/Jinja, server-rendered) works but is hard to extend.
Drivers for moving to Next.js, confirmed with the user:

1. **Richer UI/UX polish** — a more polished, modern, interactive interface than HTMX/Jinja gives.
2. **Future features** — DASH-2 (cost charts) and DASH-3 (eval lab) need rich client-side
   interactivity and data viz; a React frontend is the right substrate.
3. **Real-time / live updates** — show pipeline progress (status, OCR drain) without manual refresh.

This is a functional upgrade, not a cosmetic reskin.

## 2. Scope

**In scope (this spec):** full replacement of the HTMX dashboard with a Next.js app at
**feature parity + UI polish**, plus:
- JSON API layer on the existing FastAPI app.
- Session-cookie auth (replacing HTTP Basic).
- SSE live status updates.
- Containerization in `docker-compose`.

**Out of scope (deferred to DASH-2 / DASH-3):**
- Cost/token charts (DASH-2).
- Accuracy eval lab (DASH-3).
- Chart library adoption — metrics view uses plain CSS bars for now. Layout leaves room for
  charts later.

**Non-goals:** changing any pipeline stage logic; changing the DB schema beyond what auth/session
needs (none expected — reuses `dashboard_users`, `audit_log`).

## 3. Key Decisions (locked in brainstorm)

| Decision | Choice | Rationale |
|---|---|---|
| Data/action transport | FastAPI JSON `/api/*` + Next.js client | Control actions re-drive **Python** pipeline entry points (`handle_manifest`, `enqueue_page`, `ClassifierService`) — cannot move to TS without duplicating the pipeline. Python stays sole DB + pipeline owner; no logic duplication. |
| Old HTMX dashboard | Delete now, build fresh | User accepts no working dashboard mid-migration. Removes maintenance surface. |
| Auth | Session cookie (httpOnly, signed) | Standard for a SPA; reuses existing `dashboard_users` bcrypt table; clean logout; no creds in JS. |
| Deployment | Containerized, same box (docker-compose) | Matches local-first strategy; one origin. |
| Component library | Build from scratch (Tailwind only) | Full control over polish; zero runtime UI-lib lock-in. |
| Real-time | SSE (Server-Sent Events) | One-way status stream; simple, auto-reconnect, no extra infra. |
| Default theme | Light (dark also supported) | User selected Light direction in visual mockup; dark via token/class toggle. |
| Frontend location | `web/` at repo root | Not Python/cloud code; keeps monorepo split clean. |

## 4. Architecture

```
Browser
  ├── HTTP/JSON ──> FastAPI  /api/*        ──> queries.py / actions.py / audit.py ──> Postgres / S3 / pipeline
  └── SSE       ──> FastAPI  /api/stream   ──> DB-poll diff loop (SELECT-only)
Next.js (App Router): SSR shell + client components, TanStack Query cache, EventSource for SSE.
```

### Backend (`cloud/dashboard/`)
- **New:** `api.py` — `APIRouter` mounted at `/api`, returns JSON. Depends on `require_session`.
- **Reused unchanged:** `queries.py` (SELECT-only), `actions.py` (idempotent re-drive), `audit.py`.
- **New:** `session.py` — login/logout, signed cookie issue/verify, `require_session` dependency.
- **Deleted:** `templates/`, `static/`, the HTML-returning `router.py` (and its `Jinja2Templates`
  wiring in `cloud/app.py`). `auth.py` (HTTP Basic) is replaced by `session.py`; keep the bcrypt
  verify helper if reusable.
- **Isolation rules preserved (locked in DASH-1):** `queries.py` never writes / never imports write
  repos; `actions.py` only re-drives existing idempotent entry points; every control action writes
  exactly one `audit_log` row (ok/error); actions never return 500 (JSON `{ok:false,message}`).

### Frontend (`web/`)
- Next.js (App Router) + TypeScript + Tailwind.
- Hand-rolled component primitives (Button, Card, Table, Badge, Dialog, Toast, ProgressBar,
  Skeleton, Input, Select).
- TanStack Query for fetching/caching; `EventSource` for SSE.
- Lucide icons (SVG, no emoji). Fonts: Fira Sans (body), Fira Code (mono — IDs, JSON, raw_text).
- Design tokens (CSS variables) for the palette below; dark mode via `class="dark"` on root.

## 5. JSON API

All endpoints under `/api`, all require a valid session except `/api/login`.

| Method | Path | Replaces | Response |
|---|---|---|---|
| POST | `/api/login` | — | sets cookie; `{user}` |
| POST | `/api/logout` | — | clears cookie; `{ok}` |
| GET  | `/api/me` | — | `{user}` or 401 |
| GET  | `/api/documents?category&status&match_status&search&offset` | `doc_list` | `{documents:[…], total, offset, limit}` |
| GET  | `/api/metrics` | `metrics` | `{status_counts, match_counts}` |
| GET  | `/api/audit?username&document_id&action` | `audit_view` | `{rows:[…]}` |
| GET  | `/api/documents/{id}` | `doc_detail` | `{doc, pages, ocr_done, structured_done}` |
| GET  | `/api/documents/{id}/pages/{n}` | `page_detail` | `{page, structured_json, raw_text}` |
| GET  | `/api/documents/{id}/pages/{n}/image` | `page_image` | `image/png` (S3 proxy, unchanged) |
| POST | `/api/documents/{id}/ingest` | `action_ingest` | `{ok, message}` |
| POST | `/api/documents/{id}/requeue-ocr` (body: `page_nums?`) | `action_requeue` | `{ok, message}` |
| POST | `/api/documents/{id}/reclassify` | `action_reclassify` | `{ok, message}` |
| GET  | `/api/stream` (SSE) | — | event stream (see §6) |

Action endpoints reuse `actions.reingest / requeue_ocr / reclassify` verbatim and the `_audit`
helper; only the response serialization changes (JSON, not toast HTML). Malformed input (e.g.
`page_nums="2,abc"`) returns `{ok:false,message}` with HTTP 200, matching current behavior.

## 6. Real-time (SSE)

- `GET /api/stream` returns `text/event-stream`. Server runs a SELECT-only poll loop (~2s),
  diffing `documents.updated_at`, emitting changed rows as:
  `data: {"document_id","status","match_status","ocr_done","ocr_total"}`.
- No new pipeline plumbing; no writes; honors `queries.py` isolation.
- Client: a single `EventSource` updates the documents table rows and the open document-detail page
  in place via TanStack Query cache writes. Auto-reconnect on drop; pauses when tab hidden.
- Heartbeat comment every ~15s to keep the connection alive through proxies.

## 7. Views & UI Polish

Style: **Data-Dense Dashboard** (KPI cards, data tables, grid layout, minimal padding, status
colors, space-efficient). Light default; dark supported.

**Palette (tokens):** primary `#1E40AF`, secondary `#3B82F6`, accent `#D97706`,
background `#F8FAFC`, foreground `#1E3A8A`, muted `#E9EEF6`, border `#DBEAFE`,
destructive `#DC2626`. Status: done=green, processing=amber, failed=red, review=indigo.

Views:
- **Login** — centered card, username/password, inline error, submit loading state.
- **Documents (home)** — KPI cards (Total / Processing / Matched / Manual review); filter chips
  (category, status, match_status) + search (reg-no / filename); sortable table with status &
  match **badges**, OCR **progress bar** (done/total); **live** row updates via SSE; pagination
  carrying active filters. Row → document detail.
- **Document detail** — header block (reg-no, category/type, status, match_status); action buttons
  (Re-ingest / Requeue OCR / Re-classify) with inline loading → toast result; page grid with
  thumbnails (image proxy) + per-page OCR status; live status via SSE.
- **Page detail** — S3 page image alongside `structured_json` (Fira Code, collapsible/pretty),
  `raw_text` (from `structured_json->>'raw_text'`), classification fields.
- **Metrics** — KPI cards + plain CSS bar breakdowns (status, match_status). Chart lib deferred.
- **Audit log** — filterable table (username / document_id / action); ok/error badges; timestamps.

**Cross-cutting (UI/UX Pro Max checklist):**
- No emoji as icons (Lucide SVG only); consistent icon family/size.
- Hover/press/focus states 150–300ms; visible focus rings; `cursor-pointer` on clickables.
- Skeleton loaders for >300ms loads; toasts auto-dismiss 3–5s, `aria-live="polite"`.
- Touch targets ≥44px; form labels visible (not placeholder-only); error near field.
- WCAG AA contrast (4.5:1 text) verified in **both** themes; color never the only signal (badge has
  text + color).
- Responsive 375 / 768 / 1024 / 1440; no horizontal scroll on mobile.
- `prefers-reduced-motion` respected; confirmation dialog before destructive re-drives.
- Tabular figures (Fira Code) for numeric/ID columns to avoid layout shift.

## 8. Containerization

- `web/Dockerfile` — multi-stage Next.js production build (standalone output).
- `docker-compose.yml` — new `web` service; Next.js `rewrites` proxy `/api/*` to the FastAPI
  service so the browser sees one origin (avoids CORS + keeps the cookie first-party).
- `make` targets: `web-dev` (Next dev server), `web-build`, and dev wiring alongside `make serve`.
- FastAPI keeps serving `/api`; it no longer serves dashboard HTML.

## 9. Testing

- **Backend (pytest):** new `/api/*` — login/logout/me (cookie set/clear, 401 unauth), each GET
  endpoint JSON shape, each action JSON `{ok,message}` incl. failure path + audit row written, SSE
  endpoint smoke (emits an event, heartbeat). Reuses `tests/cloud/conftest.py` engine-dispose
  fixture. Preserve isolation assertions from DASH-1.
- **Frontend (Vitest + Testing Library):** component tests for Table, Badge, ProgressBar, filter
  controls; 1–2 integration tests against a mocked API client; auth-redirect guard.

## 10. Migration / Cutover Order

1. Add backend: `session.py` + `api.py` (JSON), wire into `cloud/app.py`. (The old HTML router may
   stay for the duration of this single migration PR as scaffolding, but is **not** kept past
   cutover — see step 6. This is "delete on cutover," not "keep both," consistent with §3.)
2. Scaffold `web/` (Next.js, Tailwind, tokens, primitives).
3. Build views against the JSON API (login → documents → detail → page → metrics → audit).
4. Wire SSE.
5. Containerize + compose + make targets.
6. Delete HTMX `templates/`, `static/`, HTML `router.py`, Jinja wiring; remove HTTP Basic `auth.py`.
7. Verify: full pytest green; manual smoke (`docker-compose up`, seed user, walk all views/actions).

## 11. Risks / Open Items

- **Build-from-scratch components** = more frontend effort than a UI lib; accepted for control.
  Mitigation: a small, disciplined primitives set; do not over-build.
- **SSE poll loop** is a pragmatic stand-in; if it proves chatty, revisit (LISTEN/NOTIFY) later —
  out of scope now.
- **Session secret** management: needs a `SESSION_SECRET` env var (add to `.env.example`, config).
- Image proxy keeps the DASH-1 deferred behavior (500-vs-404 on S3 miss) unless trivially improved.

## 12. Success Criteria

- All 6 DASH-1 views + 3 actions reachable in Next.js at parity, behind session auth.
- Live status updates visible without refresh.
- Both themes meet WCAG AA; UI/UX Pro Max pre-delivery checklist passes.
- Full backend pytest green; frontend component/integration tests green.
- `docker-compose up` serves the dashboard on one origin; manual smoke passes.
