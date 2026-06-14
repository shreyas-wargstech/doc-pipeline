# Cost & Usage Tracking (DASH-2) — Design

**Date:** 2026-06-15
**Branch:** `feat/observability-page` (continues the Observability work; retrieval runs concurrently on `main`)
**Roadmap:** DASH-2 — instrument OpenRouter calls → `cost_events` → surface on the Observability page.

## Context

Every OpenRouter call already returns full usage + cost inline (`response.usage` with OpenRouter's `cost` extension), but all ~10 call sites discard it. OpenRouter has **no inference webhooks** — the realistic "delivery status" signal is per-call success/error, captured at the call site. This feature captures token/cost per call, stores it, and surfaces spend on the Observability page (which currently shows a "DASH-2 later" note).

OpenRouter `usage` shape (relevant fields): `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost` (USD credits charged), `prompt_tokens_details.cached_tokens`, `completion_tokens_details.reasoning_tokens`.

## Capture approach — shared wrapper + contextvar sink

The sync `_*_sync` helpers run in worker threads (via `anyio.to_thread`) and have no DB session. So capture is split:

- **`shared/llm_usage.py`** (new):
  - `CostEvent` (pydantic): `stage, model, document_id|None, page_num|None, prompt_tokens, completion_tokens, total_tokens, cost: float, status: "ok"|"error", detail|None`.
  - `_SINK: ContextVar[list[CostEvent] | None]` — active collector, default `None`.
  - `collecting() -> contextmanager` — sets a fresh list as the sink, yields it, resets on exit. `anyio.to_thread` copies the context into the worker thread, so appends from the sync call are visible to the caller (shared list object).
  - `chat_completion(client, *, stage, model, document_id=None, page_num=None, **create_kwargs)` — calls `client.chat.completions.create(model=model, **create_kwargs)`, extracts usage via `_extract`, appends a `CostEvent` to the active sink (no-op if none), returns the raw response. On `OpenAIError` it appends a `status="error"` event and re-raises.
  - `_extract(response, ...)` — defensive `getattr` reads (usage or cost may be absent for some models/tests) → `CostEvent`.
  - `async def persist_cost_events(session, events)` — bulk insert; no-op on empty.

- **Call sites**: replace `client.chat.completions.create(model=model, ...)` with `chat_completion(client, stage=<name>, model=model, document_id=..., page_num=..., ...)`. Sites without doc context pass `None`. (Stage names: `ocr_vlm`, `ocr_classify`, `classifier`, `structure`, `document_type`, `index_summary`, `index_entities`, `index_keywords`, `retrieval_parse`.)

- **Flush points** (where a session exists): wrap stage processing in `with collecting() as sink:` then `await persist_cost_events(session, sink)`. Paid stages first: OCR consumer, classifier, structure. Index/retrieval flush added with their session scope. Capture is a no-op until a flush point wraps it, so partial rollout is safe.

## Storage — `cost_events` table

```sql
CREATE TABLE IF NOT EXISTS cost_events (
    id                BIGSERIAL   PRIMARY KEY,
    ts                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stage             TEXT        NOT NULL,
    model             TEXT        NOT NULL,
    document_id       TEXT,                      -- nullable (retrieval has none); no FK (keep events if doc purged)
    page_num          INTEGER,
    prompt_tokens     INTEGER     NOT NULL DEFAULT 0,
    completion_tokens INTEGER     NOT NULL DEFAULT 0,
    total_tokens      INTEGER     NOT NULL DEFAULT 0,
    cost              DOUBLE PRECISION NOT NULL DEFAULT 0,
    status            TEXT        NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','error')),
    detail            TEXT
);
CREATE INDEX IF NOT EXISTS idx_cost_events_ts       ON cost_events (ts DESC);
CREATE INDEX IF NOT EXISTS idx_cost_events_stage    ON cost_events (stage);
CREATE INDEX IF NOT EXISTS idx_cost_events_document ON cost_events (document_id);
```

Added to `db/schema.sql` (authoritative) + a one-shot `scripts/apply_cost_events.py` (mirrors `apply_bookmarks.py`) for the live DB without a flush.

## Read API — `cloud/dashboard`

- `cloud/dashboard/cost_queries.py` (new): `cost_summary(session, *, since=None)` → totals (cost, prompt/completion/total tokens, call count, error count); `cost_by_stage`, `cost_by_model` → `{key: {cost, total_tokens, calls}}`; `recent_cost_events(session, *, limit, stage=None)` → rows for a table.
- `cloud/dashboard/api.py`: `GET /api/costs` → `{summary, by_stage, by_model}`; `GET /api/costs/events?stage=&limit=` → `{rows}`. Both behind `require_session`.
- Optional `GET /api/costs/credits` → proxy `GET {base}/credits` with the server key → `{balance, usage}` for a "credits remaining" KPI. (Server-side only; key never reaches the browser.)

## UI — Observability page (additive)

Replace the deferred-note paragraph with a **Cost & usage** section:
- KPI row: Total spend (USD), Total tokens, LLM calls, Errors (tone=danger), and Credits remaining (if `/api/costs/credits` ok).
- Two `MetricBars`: **cost by stage**, **cost by model** (values = USD, formatted).
- Recent expensive calls `Table`: ts, stage, model, document (link), tokens, cost, status badge — clickable into the existing `Drawer` pattern for detail.
- New hooks `useCosts()` / `useCostEvents()` (mirror `useMetrics`/`useAudit`); types in `web/lib/types.ts`; a `fmtUsd` helper in `web/lib/format.ts`.

## Testing

- Backend unit: `shared/llm_usage.py` (`_extract` from a fake response incl. missing-usage fallback; `chat_completion` appends to sink incl. error path; `collecting` set/reset; `persist_cost_events` bulk + empty no-op). `cost_queries` aggregations (mocked session). `api` endpoints forward params + shape (mirror audit tests). One instrumented site test (classifier emits a CostEvent when a sink is active).
- Frontend: `cost-section` render (KPIs, bars, table), `fmtUsd`, hooks query-key/url. Extend `observability-page.test.tsx`.
- Gates: `tsc`, web suite, `next build`; backend `pytest -m "not integration"`.

## Phasing (committable steps)

1. `cost_events` schema + `apply_cost_events.py`.
2. `shared/llm_usage.py` + tests.
3. Instrument call sites + flush points (paid stages first), tests.
4. `cost_queries` + `/api/costs*` + tests.
5. Observability UI section + hooks + tests.

## Isolation

Confined to the worktree. New files + additive edits; the only shared-code edits are the LLM call sites (one-line swaps) — `shared/` and `cloud/` stages, which the retrieval task is not modifying except `cloud/retrieval/query_parser.py` (one call site). That single overlap is a one-line wrapper swap; flag at merge.
