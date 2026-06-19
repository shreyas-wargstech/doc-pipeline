# Aether Redesign — Conversational Canvas + LLM-Tool Fallback

> **Date:** 2026-06-19
> **Phase:** 5 (Frontend feature build-out) — Aether Chat Interface, redone.
> **Status:** Design approved, pending spec review.
> **Scope:** Redesign the existing Aether surface (`web/app/(dash)/aether/page.tsx`) into a
> modern conversational canvas with typed result cards, a command palette, a welcome hero,
> and an LLM-tool fallback behind the existing zero-LLM fast-path router. UI built with
> `/crafting-alive-interfaces` on the warm-editorial foundation.

---

## 1. Problem

The shipped Aether is functional but thin:

- The backend (`cloud/aether_chat/service.py`) already returns **rich structured `tool_calls`
  payloads** (autopsy reports, inspector stages, health checks, etc.), but the frontend
  **throws that data away** — it renders only the markdown `content` plus a tiny tool-name
  `Badge`. The most valuable data never reaches the screen.
- It only answers 6 hardcoded intents. Anything outside the regex patterns falls to a static
  help message. There is no path to open-ended conversation.
- There is no discoverability layer — a new operator cannot tell what Aether can do.
- Visually it is a generic bubble list: no welcome state, no card system, minimal motion.

The user wants: (a) a genuinely conversational assistant with an LLM fallback that is **not
restricted** to a fixed list of use cases, (b) structured **card results**, and (c) a modern,
"alive" UI redesign with properly aligned components.

## 2. What we are building

A two-tier conversational assistant and a four-state UI.

### Backend (two-tier orchestration, additive)

```
User msg ─► POST /api/chat ─► AetherOrchestrator
                               ├─ 1. fast-path regex router (EXISTING, free, instant)
                               │      matches 1 of 6 intents → typed ToolCall(s)
                               └─ 2. LLM fallback (NEW, gated by aether_llm_enabled)
                                      google/gemini-2.5-flash with tool-calling, can invoke
                                      the SAME services as tools:
                                      autopsy · narrative · context · identity ·
                                      inspector · health · search
        ◄── ChatResponse { role, content (markdown), tool_calls[] (typed) } ──┘
```

- The HTTP response **envelope is unchanged**: `{ role, content, tool_calls[] }`. Both tiers
  emit the same shape, so the frontend renderer is agnostic to which tier produced the turn.
- The LLM path is gated behind a new default-off setting `aether_llm_enabled` (mirrors the
  existing `self_healing_enabled` / `monitor_enabled` pattern in `shared/config.py`). With the
  flag off, or with no `OPENROUTER_API_KEY`, behavior is exactly today's (fast-path + static
  help fallback). Nothing regresses.
- All LLM calls go through the existing `shared/llm_usage.chat_completion` wrapper so spend is
  recorded in `cost_events` under site `aether_llm` (consistent with `ocr_vlm`,
  `classifier`, `structure`, etc.).

### Frontend (four states)

1. **Welcome hero** — ambient entrance shown when the thread is empty: capability gallery
   (4 cards), recent-thread list, command-first input.
2. **Command palette** — `/`-triggered overlay with grouped query templates, keyboard
   navigation, and a free/instant-vs-LLM indicator. Backed by the existing
   `GET /api/search/suggest` ("Aether autocomplete suggestions") plus a static template set.
3. **Conversation canvas** — the message stream. Assistant turns render markdown `content`
   plus one `<ToolResultCard>` per `tool_call`.
4. **Rich result cards** — a discriminated renderer that switches on `tool_call.tool` and
   renders a purpose-built card per kind, with full data-viz (SVG consistency gauge,
   horizontal pipeline timeline, health grid) and contextual action buttons that deep-link
   into the rest of the app.

## 3. Backend design

### 3.1 Tool extraction

Refactor `cloud/aether_chat/service.py` so each of the 6 existing intent handlers becomes an
**independently callable async tool function** with a typed result dict carrying a `kind`
discriminator. No behavior change to the handlers themselves — this is a structural
extraction so both the regex router and the LLM loop can call them.

```python
# cloud/aether_chat/tools.py  (new)
async def tool_autopsy(document_id: str) -> dict     # {"kind": "autopsy", ...report.to_dict()}
async def tool_narrative(document_id: str) -> dict    # {"kind": "narrative", ...}
async def tool_context(document_id: str) -> dict      # {"kind": "context", ...}
async def tool_identity(document_id: str) -> dict     # {"kind": "identity", ...}
async def tool_inspector(document_id: str) -> dict    # {"kind": "inspector", ...}
async def tool_health() -> dict                       # {"kind": "health", ...}
async def tool_search(query: str) -> dict             # {"kind": "search", ...} NEW
```

`tool_search` wraps the existing `cloud/retrieval/service.py::retrieve_documents` (the same
service behind `/api/search`), returning document-card payloads. This is what powers "show me
all pages for Dr. Sharma" — but as a general retrieval tool, not a hardcoded feature.

The 6 existing handlers in `service.py` are rewritten to delegate to these tool functions so
there is a single source of truth for each operation.

### 3.2 Orchestrator

```python
# cloud/aether_chat/service.py  (modified)
async def chat(message: str, document_id: str | None = None) -> ChatResponse:
    intent = _detect_intent(message)            # existing regex
    if intent is not None:
        return await _run_fast_path(intent, message, document_id)   # existing behavior
    # No fast-path match:
    if settings.aether_llm_enabled and settings.openrouter_api_key:
        return await run_llm_fallback(message, document_id)         # NEW
    return _help_response()                      # existing static help
```

### 3.3 LLM fallback (`cloud/aether_chat/llm.py`, new)

- A bounded tool-calling loop (max N iterations, e.g. 4) using `chat_completion` with the 7
  tools exposed as function definitions.
- System prompt instructs the model: answer only from tool results, never invent document
  data, prefer the cheapest tool that answers the question, keep responses concise.
- Each tool the model invokes is appended to `ChatResponse.tool_calls` with its typed `kind`
  result, so the frontend renders the same cards regardless of tier.
- Graceful degradation: LLM/network error → return a short "I couldn't complete that"
  assistant turn (no crash), matching the `classifier`/`structure` graceful-fallback rule.
- Cost recorded via the `collecting()` contextvar sink → `cost_events` site `aether_llm`.

### 3.4 Config

Add to `shared/config.py`: `aether_llm_enabled: bool = Field(False, alias="AETHER_LLM_ENABLED")`.
Document the flag in `.env.example`.

## 4. Frontend design

All UI built on the existing warm-editorial foundation: Fraunces (display) / Inter (body) /
JetBrains Mono (identifiers), cream `#F9F7F4`, teal primary `#0D9488`, amber secondary
`#C49A6C`, shadcn/ui primitives, `motion/react`. Light-only. Built with
`/crafting-alive-interfaces`.

### 4.1 New / changed files

```
web/app/(dash)/aether/page.tsx                 rewritten — orchestrates the 4 states
web/components/aether/WelcomeHero.tsx           new — empty-state hero + capability gallery + recent
web/components/aether/CommandPalette.tsx        new — "/" overlay, grouped templates, keyboard nav
web/components/aether/Composer.tsx              new — input bar w/ "/" trigger + suggestion chips
web/components/aether/MessageBubble.tsx         extracted from current page
web/components/aether/TypingIndicator.tsx       extracted from current page
web/components/aether/ToolResultCard.tsx        new — discriminated renderer (switch on tool kind)
web/components/aether/cards/AutopsyCard.tsx     new (shares style w/ existing AutopsyPanel)
web/components/aether/cards/IdentityCard.tsx    new — SVG consistency gauge
web/components/aether/cards/InspectorCard.tsx   new — horizontal pipeline timeline
web/components/aether/cards/HealthCard.tsx      new — status grid
web/components/aether/cards/NarrativeCard.tsx   new — prose + doc link
web/components/aether/cards/ContextCard.tsx     new — related-docs / history list
web/components/aether/cards/SearchResultsCard.tsx  new — doc result cards + "See all in retrieval"
web/hooks/useChat.ts                            extended — recent threads, optional context
web/lib/types.ts                                extended — ToolCall result union by `kind`
```

### 4.2 Typed card rendering

`tool_call.result` becomes a discriminated union keyed on `kind`. `ToolResultCard` switches on
it and renders the matching card. An unknown `kind` falls back to a compact key/value card so
new backend tools never break the UI.

```ts
type ToolResult =
  | { kind: "autopsy";   stages: AutopsyStage[]; overall_status: string; recommendation: string | null }
  | { kind: "identity";  consistency_score: number; summary: string; fields: FieldAgreement[] }
  | { kind: "inspector"; stages: InspectorStage[]; overall_status: string }
  | { kind: "health";    overall: string; checks: HealthCheck[] }
  | { kind: "narrative"; document_id: string; narrative: string }
  | { kind: "context";   related_documents: DocRef[]; practitioner_history: unknown }
  | { kind: "search";    hits: DocHit[]; total: number };
```

### 4.3 Card data-viz (full richness, per approved mockups)

- **IdentityCard** — SVG arc gauge (stroke-dasharray) for `consistency_score`, plus per-field
  agreement rows (registration_no / name / dob with check / partial / missing icons).
- **InspectorCard** — horizontal 6-node pipeline rail (Ingest → OCR → Structure → Match →
  Persist → Index) with a filled progress track; current stage pulses amber, done = teal.
- **HealthCard** — 4-up metric grid (DB latency, queue depth, credit balance) with status
  dots; amber dot for warnings (e.g. low credit).
- **AutopsyCard** — stage rows with status dots + a recommendation callout (reuses the visual
  language of the existing `web/components/AutopsyPanel.tsx`).
- **SearchResultsCard** — compact document result rows (reuses styling from
  `web/components/retrieval/ResultCard.tsx`) with a "See all in retrieval" deep link.

### 4.4 Action buttons (launchpad, not dead end)

Cards carry contextual actions that route into existing surfaces:

- AutopsyCard → "Open form page" (`/documents/{id}/pages/{n}`), "Re-run match" (existing
  requeue/eval endpoint).
- SearchResultsCard → row click → `/documents/{id}`; "See all in retrieval" → `/retrieval?q=`.
- InspectorCard / IdentityCard → "Open document" → `/documents/{id}`.

### 4.5 Command palette + composer

- Composer input: typing `/` at the start opens `CommandPalette`. Suggestion chips sit above
  the input for one-tap templates.
- Palette: grouped templates (Diagnose / Find / System), arrow-key navigation, Enter to select
  (selecting a template that needs a doc id inserts a placeholder for the user to fill), Esc to
  close. Footer shows "free · instant · no LLM" for fast-path templates.
- Live suggestions from `GET /api/search/suggest` merge with the static template set.

### 4.6 Motion (crafting-alive-interfaces)

Staggered card entrance, typing indicator (existing), `AnimatePresence` on palette open/close,
ambient gradient on the welcome hero, hover lift on capability/result cards, gauge arc animates
from 0 to value on mount, pipeline track animates its fill. No bare spinners — content-shaped
skeletons for in-flight tool results.

## 5. Data flow

1. User types (or picks a palette template) → `useChat.send(message, documentId?)`.
2. Optimistic user bubble appended; `POST /api/chat`.
3. Backend: fast-path hit → typed tool_calls; else (flag on) LLM loop → typed tool_calls; else
   help text.
4. Response appended as an assistant turn: markdown `content` + N `<ToolResultCard>`.
5. Recent threads persisted client-side (localStorage) for the welcome hero list.

## 6. Error handling

| Failure | Behavior |
|---|---|
| LLM unavailable / no API key / flag off | Fall back to fast-path; unmatched → static help. No crash. |
| Tool raises (doc not found) | Card renders an inline empty/error state; conversation continues. |
| Malformed LLM tool args | Caught in the loop; surfaced as a short "I couldn't complete that" turn. |
| Unknown `tool_call.kind` on frontend | Generic key/value fallback card. |
| `/api/chat` non-2xx | Assistant error bubble; input stays enabled for retry. |

## 7. Testing

**Backend (pytest, mocked externals, TDD):**
- Each tool function unit-tested in isolation (success + not-found).
- `tool_search` returns the expected card shape from a mocked `retrieve_documents`.
- Orchestrator: fast-path hit returns existing shape; unmatched + flag-on dispatches to LLM
  (mocked `chat_completion`); unmatched + flag-off returns help text.
- LLM loop: tool-call dispatch, max-iteration bound, graceful error → safe turn, cost recorded.

**Frontend (vitest + RTL, TDD):**
- `ToolResultCard` renders each `kind` correctly; unknown kind → fallback card.
- IdentityCard gauge reflects score; InspectorCard marks current stage; HealthCard flags warn.
- CommandPalette: `/` opens, arrow nav, Enter selects, Esc closes, suggestions merge.
- WelcomeHero renders on empty thread; hides once a message exists.
- Error states for failed `/api/chat`.

**Gates:** `uv run pytest -m "not integration"` green for new backend tests;
`cd web && npx tsc --noEmit` → 0; `cd web && next build` green; `vitest run` green.

## 8. Out of scope (v1)

- WebSocket live document streaming (separate deferred thread; cards show point-in-time data).
- Engine Room and Document Autopsy redesigns (separate Phase 5 items; this spec is Aether only).
- Persisting chat threads server-side (recent list is client-side localStorage only).
- Multi-turn LLM memory beyond the current request (each `/api/chat` call is stateless server-side).

## 9. Locked decisions for this work

- Response envelope stays `{ role, content, tool_calls[] }` — additive only.
- LLM fallback is **default-off** (`aether_llm_enabled`) and routes through
  `shared/llm_usage.chat_completion` with `cost_events` site `aether_llm`.
- Fast-path regex router remains the first, free, instant tier — the LLM never runs when a
  known intent matches.
- `tool_search` wraps the existing `retrieve_documents`; no new retrieval logic.
- Frontend cards reuse the warm-editorial token system and existing card styling
  (`AutopsyPanel`, `ResultCard`) where applicable.
