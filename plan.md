# Phase 5 Plan — Aether Chat + Engine Room + Document Autopsy

## Overview
Build three new UI surfaces on the warm-editorial shadcn+motion foundation. Backend APIs already exist for all three; this is frontend + minor backend wiring.

## Skill: `crafting-alive-interfaces`
- All content animates in (blur-fade, stagger)
- Hover/focus/press states on every interactive element
- Skeleton loaders shaped like real content
- Theme tokens only (no inline hex)
- One transition on every state change
- Ambient motion (subtle pulse/gradient)

---

## Stage 1 — Engine Room v1 Page

### Route: `/engine-room` (new nav item in AppShell, admin-only)

### Sections (top to bottom):
1. **Health Panel** — `GET /api/engine/health`
   - Cards per dependency (Postgres, S3, OpenRouter, Tesseract)
   - Status badge: ok/warn/error with color + icon
   - Stagger entrance

2. **Diagnostics Panel** — `GET /api/engine/diagnostics`
   - "Run diagnostics" button → fetch + expand results
   - Accordion list of checks with pass/fail

3. **Parameter Tuner** — `GET /api/engine/parameters`, `POST /api/engine/parameters/{name}`
   - Table of parameters (name, value, source)
   - Inline edit → dialog with test-on-sample option
   - Suggestions from `GET /api/engine/tuning/suggestions`

4. **A/B Test Panel** — `POST /api/engine/ab-test`
   - Form: hypothesis, sample size, variant JSON
   - Results: comparison table (baseline vs variant metrics)

5. **Cost Summary** — `GET /api/engine/costs/summary`
   - KPI cards + per-stage breakdown

6. **Document Inspector** — `GET /api/engine/inspector/{document_id}`
   - Input field for doc ID → stage-by-stage pipeline report

### Backend additions (if any):
- None — all endpoints exist in `cloud/dashboard/api.py`

---

## Stage 2 — Document Autopsy UI

### Integration: Document detail page (`/documents/[id]`)
- New tab/panel: "Autopsy"
- Calls `GET /api/documents/{id}/autopsy`
- Displays `AutopsyReport` as a timeline/stage cards:
  - Stage name + status badge (success/partial/failed/pending/not_applicable/manual_review)
  - Detail text
  - Recommendation callout at bottom (if present)
- Entrance: stagger cards from left

### Component: `AutopsyPanel`
- Reusable — could also be used on eval review page

---

## Stage 3 — Aether Chat Interface

### Route: `/aether` (new nav item, all roles)

### Backend: Simple intent router (no LLM cost)
- `POST /api/chat` — accepts `{message, document_id?}`
- Regex-based intent matching:
  - "autopsy|why.*fail|what.*wrong" → `generate_autopsy(doc_id)`
  - "narrative|summary|tell me about" → `generate_narrative(doc, pages)`
  - "context|related|similar" → `build_context(...)`
  - "identity|consistency|match" → `generate_consistency_report(...)`
  - "health|status|engine" → `check_all()`
  - fallback → friendly help message listing available commands
- Returns `{role:"assistant", content:string, tool_calls?:{tool,result}[]}`

### Frontend:
- `ChatThread` — scrollable message list
- `ChatMessage` — user (right, teal) / assistant (left, warm)
- `ChatInput` — rounded input with send button + loading state
- Document context selector (if no doc_id in URL)
- Skeleton typing indicator during fetch
- Ambient: faint gradient behind chat area

### Types additions:
- `ChatMessage`, `ChatRequest`, `ChatResponse`

---

## Verification
1. `cd web && npx tsc --noEmit` → 0 errors
2. `cd web && next build` → all routes compile
3. `cd web && vitest run` → existing tests pass (fix any drift)
4. Backend: `uv run pytest -m "not integration"` → green

---

## Execution Order
1. Engine Room (biggest, pure frontend)
2. Document Autopsy (medium, frontend + minor integration)
3. Aether Chat (complex, backend + frontend)
4. Verify + log
