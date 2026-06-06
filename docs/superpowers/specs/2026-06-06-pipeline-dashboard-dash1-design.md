# DASH-1 — Operational Dashboard (design)

> **Status:** Approved design, ready for implementation plan.
> **Date:** 2026-06-06 · **Scope:** DASH-1 only (operational monitor + control).
> Cost tracking (DASH-2) and accuracy eval lab (DASH-3) are separate specs.
> Parent plan + decomposition: TECH_DECISIONS §19, auto-memory `dashboard-plan.md`.

## 1. Purpose

A web dashboard to **monitor and control** the document pipeline, which today is
driven only via `make` targets, SQS, and the `/pipeline/notify` HTTP shim. DASH-1
delivers, against state that already exists in Postgres/S3:

- **Monitor:** list documents with their pipeline stage status; drill into a
  document and its pages; inspect OCR text, structured JSON, classification, the
  S3 page image, and the reference-data match; view match-rate aggregates.
- **Control:** trigger (re-run) ingest, requeue OCR, re-classify — all as
  idempotent re-drives of existing stage entry points.
- **Governance:** HTTP Basic auth + an audit trail on every control action
  (deployment target = shared internal, few users).

**Out of scope for DASH-1 (YAGNI):** charts, websockets/live refresh, bulk
multi-doc operations, editing extracted data, cost/tier views (DASH-2), accuracy
evals / tier comparison (DASH-3).

## 2. Tech & dependencies

- **FastAPI + HTMX/Jinja**, server-rendered, mounted on the existing
  `cloud/app.py` (same uvicorn process, `make serve`). Rationale + rejected
  alternatives (React SPA, Streamlit): TECH_DECISIONS §19.
- New deps: `jinja2`, `python-multipart` (form posts), `passlib[bcrypt]`
  (password hashing). HTMX is vendored as a static file (no JS build step).

## 3. Package layout

```
cloud/dashboard/
  __init__.py
  router.py        # APIRouter — all routes (full pages + HTMX partials)
  queries.py       # READ-ONLY aggregate queries (doc list, status counts, match-rate)
  actions.py       # control actions: thin wrappers over existing stage entry points
  auth.py          # HTTP Basic dependency + current-username extraction
  audit.py         # write + read audit_log rows
  templates/       # base.html, doc_list.html, doc_detail.html, page_detail.html,
                   #   metrics.html, audit_log.html + HTMX partials
  static/          # htmx.min.js (vendored) + dashboard.css
```

`cloud/app.py` gains exactly one wiring line:
`app.include_router(dashboard_router, prefix="/dashboard")`.

**Boundary rules (isolation):**
- `queries.py` is **read-only**; it issues `SELECT`s only and never imports the
  write repositories.
- `actions.py` **only** calls existing entry points — `handle_manifest()`,
  `enqueue_page()`, the classifier service, and existing repo methods
  (`update_fields`, `bulk_update_ocr_status`). The dashboard never performs a
  stage's DB write itself; it re-drives the stage.

## 4. Read model (monitor)

### 4.1 Document list — `GET /dashboard/`
Paginated table. Columns: short `document_id`, `document_category`,
`document_type`, `status`, `match_status`, `page_count`, OCR progress
(done/total), `updated_at`. Filters: category, status, match_status, and a
free-text term matched against `registration_no` / `original_filename`.

New read queries in `queries.py`:
- `list_documents(*, category, status, match_status, search, limit, offset) -> list[Row]`
  — joins a per-document OCR-progress subquery (`count(*) filter (where ocr_status='done')`
  over `pages`).
- `count_documents(filters) -> int` — for pagination.

### 4.2 Document detail — `GET /dashboard/doc/{document_id}`
Document row + a per-page strip showing the **derived stage state**:

| Stage | Derived from |
|---|---|
| Ingested | `documents` row exists |
| Classified | `document_type` present (heuristic — the schema has no explicit "classifier ran" flag; `document_category` alone can't be distinguished from the NAS hint, so we key off `document_type`, which only the classifier sets) |
| OCR | per-page `ocr_status` (pending/queued/done/failed/skipped) |
| Structured | `pages.structured_json` present |
| Persisted | **shown as "not implemented"** until `cloud/persist/` is built |

Reuses `DocumentRepository.get()` + `PageRepository.list_for_document()`.

### 4.3 Page detail — `GET /dashboard/doc/{document_id}/page/{page_num}`
Shows `raw_text`, pretty-printed `structured_json`, `confidence_score`,
`language_detected`, `page_type`, plus the **S3 page image**. The image is
served via a proxy endpoint `GET /dashboard/doc/{id}/page/{n}/image` that issues
a short-lived presigned URL (or streams bytes) from `s3_key_image` — keeps S3
creds server-side.

### 4.4 Metrics — `GET /dashboard/metrics`
Aggregate counts of `documents.match_status` and `documents.status`
(the "match-rate" eval), computed directly from Postgres. No new plumbing.

## 5. Control actions

Each is a `POST` returning an HTMX partial (success/error toast). Each wraps an
existing **idempotent** entry point, so a double-submit cannot corrupt state.

| Action | Route | Wraps | Idempotency basis |
|---|---|---|---|
| Trigger / re-run ingest | `POST /dashboard/doc/{id}/ingest` | Fetch `documents/<id>/manifest.json` from S3 → `Manifest.model_validate_json` → `handle_manifest()` | `ON CONFLICT` upserts in ingest |
| Requeue OCR (whole doc or selected `page_nums`) | `POST /dashboard/doc/{id}/requeue-ocr` | Build `OcrPageMessage` per page (category from doc row, `s3_key`/`page_type`/etc. from pages) → `enqueue_page()` → `bulk_update_ocr_status(..., 'queued')` | SQS FIFO dedup `<doc>:<page>`; consumer idempotent on `page_id` |
| Re-classify | `POST /dashboard/doc/{id}/reclassify` | Classifier service on the doc's cover text → `DocumentRepository.update_fields(document_category=..., document_type=...)` | whitelisted targeted UPDATE |

**Trigger-ingest semantics (locked):** re-runs from the document's stored
`manifest.json` in S3. Uploading a brand-new PDF remains a NAS-side concern and
is explicitly out of scope for DASH-1.

## 6. Auth + audit

### 6.1 Auth
HTTP Basic via a FastAPI dependency applied to the whole dashboard router.
Credentials live in a new `dashboard_users` table (`username` + bcrypt
`password_hash`), seeded by `scripts/add_dashboard_user.py`
(`python -m scripts.add_dashboard_user <username>` → prompts for password,
inserts/updates hash). Basic yields the username for audit with no login-form
UI. Cookie-session/SSO is a clean future swap (the dependency is the only seam).

### 6.2 Audit
New `audit_log` table. Every **control** action writes exactly one row; read
views are not audited.

```
audit_log(
  id           BIGSERIAL PK,
  ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
  username     TEXT        NOT NULL,
  action       TEXT        NOT NULL,   -- 'ingest' | 'requeue_ocr' | 'reclassify'
  document_id  TEXT,                   -- nullable (action may be doc-less)
  params       JSONB       NOT NULL DEFAULT '{}',  -- e.g. {"page_nums":[2,3]}
  result       TEXT        NOT NULL,   -- 'ok' | 'error'
  detail       TEXT                    -- error message / short summary
)
```

Viewable at `GET /dashboard/audit` (filter by username / document_id / action).
`audit.py` exposes `record(session, *, username, action, document_id, params,
result, detail)` and `list_audit(filters, limit, offset)`.

## 7. Schema changes

Two **additive** tables appended to `db/schema.sql` (`audit_log`,
`dashboard_users`) — no migration risk, no change to existing tables. An init
step (`scripts/init_postgres.py` verify list, or a dedicated idempotent step)
confirms they exist. No change to documents/pages/reference_data.

## 8. Error handling

- Control actions wrap their body in try/except: on failure they log via
  structlog, write an `audit_log` row with `result='error'` and the message in
  `detail`, and return an error-toast partial (HTTP 200 with error markup, so
  HTMX swaps it in) — never an uncaught 500.
- Read views catch query errors and render an inline message rather than 500ing.
- The app's existing global `Exception` handler stays as the final backstop.

## 9. Testing

Unit tests under `tests/cloud/` using FastAPI `TestClient` + mocked
externals (repos, S3, SQS, classifier), mirroring the existing mocked-externals
pattern:

- **Auth:** missing/incorrect Basic creds → 401; valid creds → 200.
- **Read views:** doc list / doc detail / page detail / metrics each render with
  representative mocked data; filters narrow results.
- **Control actions:** each calls its wrapped entry point exactly once with the
  right arguments; `audit_log` row written on **both** success and error paths;
  page-image proxy returns bytes/redirect.
- **Audit view:** renders rows; filters apply.

Integration test (optional, `@pytest.mark.integration`): against the real DB,
seed a document, hit `/dashboard/` and a control action, assert an `audit_log`
row appears.

## 10. Implementation order (for the plan)

1. Schema: `audit_log` + `dashboard_users` tables + init verification.
2. `auth.py` (Basic dependency) + `scripts/add_dashboard_user.py`.
3. `audit.py` (record + list).
4. `queries.py` (read-only aggregates).
5. `actions.py` (three control wrappers).
6. `router.py` + templates + vendored HTMX/CSS.
7. Wire router into `cloud/app.py`; add deps to `pyproject.toml`; `make` note.
8. Tests throughout (TDD per unit).

## 11. Open questions / assumptions

- **Assumption:** the document's `manifest.json` is reliably present at
  `documents/<document_id>/manifest.json` (per the locked S3 layout). If a doc
  predates that guarantee, re-run ingest surfaces a clean error toast.
- **Assumption:** re-classify can derive cover text the same way the classifier
  service already does (PyMuPDF text layer → Tesseract fallback); the dashboard
  reuses that path rather than reimplementing it.
- Persisted-stage status is a placeholder until `cloud/persist/` exists.
