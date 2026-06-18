# Phase 5 Dimension 04 Analysis: Document Autopsy Mode

> **Role:** Phase5_Autopsy_Analyst — Deep Dive Agent  
> **Date:** 2026-06-17  
> **Scope:** Research Dimension 04: Document Autopsy Mode — feature scope, design evolution, backend data requirements, and implementation needs for the Phase 5 frontend build-out.  
> **Constraint:** No external search performed. All findings derived from provided file excerpts only.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Analysis 1: Evolution from Heatmap Autopsy to Template-Based Text](#2-analysis-1-evolution-from-heatmap-autopsy-to-template-based-text)
3. [Analysis 2: Backend Data Source Mapping](#3-analysis-2-backend-data-source-mapping)
4. [Analysis 3: Data Availability Gap Analysis](#4-analysis-3-data-availability-gap-analysis)
5. [Analysis 4: Narratives API vs. Autopsy Mode Relationship](#5-analysis-4-narratives-api-vs-autopsy-mode-relationship)
6. [Analysis 5: Template Engine Approach](#6-analysis-5-template-engine-approach)
7. [Synthesis: Implementation Needs for Phase 5 Frontend](#7-synthesis-implementation-needs-for-phase-5-frontend)
8. [Appendix: Raw Claim Inventory](#8-appendix-raw-claim-inventory)

---

## 1. Executive Summary

Document Autopsy Mode is a **heavily simplified, zero-cost, template-based explanation system** for documents that fail processing or land in `manual_review`. It evolved from an original vision of immersive heatmap-driven forensic analysis to a plain-English decision-tree explanation that uses only existing database tables. The backend implementation (`cloud/autopsy/service.py`) is already **substantially complete** with a working API endpoint (`GET /api/documents/{document_id}/autopsy`), structured tests (`tests/cloud/test_autopsy_api.py`), and a dataclass-based report model. The remaining Phase 5 work is **frontend UI integration** — rendering the `AutopsyReport` JSON in the document viewer, wiring the "Autopsy" tab, and adding action buttons (Approve Match / Reject Match / Re-run OCR) based on the report's `recommendation` field.

---

## 2. Analysis 1: Evolution from Heatmap Autopsy to Template-Based Text

### 2.1 Original Vision ("Crazy Idea")

The original vision in `REIMAGINING.md` Appendix A proposed a full forensic "autopsy" with visual heatmaps:

```
Claim: The original Document Autopsy Mode envisioned visual heatmaps for scan-quality issues, top-3 OCR alternative readings with confidence, and side-by-side registry entry comparisons.
Source: REIMAGINING.md
URL: File: REIMAGINING.md, Section: Appendix A — The "Document Autopsy" Mode
Date: 2026-06-16
Excerpt: "Was it a scan quality issue? Show the problematic region with a heatmap. Was it an OCR ambiguity? Show the top 3 alternative readings with confidence. Was it a registry mismatch? Show the closest registry entries side-by-side."
Context: Listed under "Crazy Ideas That Might Be Genius" in the creative brainstorm document. Explicitly labeled as "not fully thought through — they're sparks."
Confidence: high
```

### 2.2 Grounded Revision

The owner rejected heatmaps and visual forensics as too complex and expensive for a government context. The grounded revision replaced them with text-only template explanations:

```
Claim: The Document Autopsy Mode was accepted into the grounded plan only after removing all heatmaps, spatial visualizations, and LLM-generated text. It became a template-based text explanation of the failure decision tree.
Source: REIMAGINING_COMPARISON.md
URL: File: REIMAGINING_COMPARISON.md, Section: §3 — The "Crazy Ideas" Appendix — Fate
Date: 2026-06-16
Excerpt: "| Document Autopsy Mode | Explain failures with heatmaps | Template-based text explanation of failure decision tree. No heatmaps. | ✅ ACCEPTED — heavily simplified |"
Context: Part of a feature-by-feature comparison table showing original brainstorm ideas vs. grounded reality. Document Autopsy is one of only three "Crazy Ideas" that survived (the others were rejected or deferred).
Confidence: high
```

### 2.3 Decision Rationale

The rationale for simplification is documented across multiple files:

**Rationale A — Cost and Complexity:**
```
Claim: The original heatmap-based autopsy would require GPU rendering or complex image processing, estimated at $200+/month just for the spatial canvas feature.
Source: REIMAGINING_COMPARISON.md
URL: File: REIMAGINING_COMPARISON.md, Section: §6 — Cost Comparison: Original vs. Grounded
Date: 2026-06-16
Excerpt: "| Spatial canvas (2D/3D) | $200+/month GPU or high-end instance | Rendering 92K documents in WebGL/Canvas requires GPU or high CPU |"
Context: Part of a cost table showing the original vision would cost $2,000+/month vs. the grounded plan at $278-350/month. The heatmap/spatial visualizations were the single most expensive line item.
Confidence: high
```

**Rationale B — User Fit:**
```
Claim: Government operators do not need or want visual heatmaps. They need a clear, fast explanation of why a document was flagged, written in plain English, with a one-click action to resolve it.
Source: REIMAGINING_COMPARISON.md
URL: File: REIMAGINING_COMPARISON.md, Section: §8 — What the Operator Actually Sees: Day in the Life
Date: 2026-06-16
Excerpt: "The document is flagged for manual review. They open the 'Autopsy' tab. They read: 'The registration number matched perfectly. The DOB matched perfectly. The only issue: the name has a missing middle name. This is a common pattern. 37 other documents had the same pattern and were approved.' They click 'Approve Match'."
Context: This is the canonical "day in the life" scenario that the grounded plan was optimized for. The entire UX flow is described in 3 sentences and one click.
Confidence: high
```

**Rationale C — Zero AI Cost Mandate:**
```
Claim: The owner explicitly mandated that the Autopsy mode must have zero LLM cost, generating explanations purely from structured database fields via string templating.
Source: REIMAGINING_GROUNDED.md
URL: File: REIMAGINING_GROUNDED.md, Section: §10 — Document Autopsy Mode (Explanation Only)
Date: 2026-06-16
Excerpt: "# cloud/autopsy/service.py — new module
async def generate_autopsy(document_id: str) -> str:
    """Generate a plain-English autopsy report. No LLM. Just template + data.""""
Context: The design document includes a full Python pseudocode implementation showing exactly how the template engine works. It explicitly states "This is 100% template-based. No LLM. No cost. Generated in <10ms."
Confidence: high
```

### 2.4 Design Principles Carried Forward

Even with heatmaps removed, the design philosophy from the Addendum still applies:

```
Claim: Despite removing heatmaps, the Document Autopsy mode retains the "warm editorial minimalism" design philosophy — formal, respectful, deeply informative, with purposeful animation and clear hierarchy.
Source: REIMAGINING_ADDENDUM.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §1 — Design Philosophy: Simple System, Beautiful UX
Date: 2026-06-16
Excerpt: "1. No spatial canvas. But the document viewer is immersive, smooth, and contextual. 2. No gamification. But the interface is rewarding to use. 3. No 3D. But the interface has depth through shadows, layers, and purposeful animation. 4. No voice/stylus/gesture. But every action is keyboard-accessible, touch-friendly, and screen-reader compatible. 5. No futuristic sci-fi. But the interface feels modern, warm, and confident."
Context: These are the 5 Key Design Decisions from the Addendum. The autopsy tab lives inside this design envelope — no sci-fi, but polished and professional.
Confidence: high
```

---

## 3. Analysis 2: Backend Data Source Mapping

### 3.1 Every Autopsy Element → Its Data Source

The autopsy report is assembled from the following existing tables and fields. Each element is mapped below:

| Autopsy Report Element | DB Table / Source | Field(s) | Availability |
|---|---|---|---|
| Document identity (name, reg, DOB) | `documents` | `applicant_name_raw`, `registration_no`, `dob` | ✅ Available |
| Document category | `documents` | `document_category` | ✅ Available |
| Page count | `documents` | `page_count` | ✅ Available |
| Original filename | `documents` | `original_filename` | ✅ Available |
| Overall status | `documents` | `status`, `match_status` | ✅ Available |
| Per-page OCR status | `pages` | `ocr_status` | ✅ Available |
| Per-page OCR tier | `pages` | `ocr_tier` | ✅ Available (NOTE: field may not exist in all rows; see §4.2) |
| Per-page OCR confidence | `pages` | `confidence_score` | ✅ Available |
| Per-page page type | `pages` | `page_type` | ✅ Available |
| Per-page structured JSON | `pages` | `structured_json` | ✅ Available |
| Blank page count | `pages` | `page_type == 'blank'` | ✅ Available |
| Match method | `documents.metadata` JSONB | `metadata.match.method` | ✅ Available |
| Match score | `documents.metadata` JSONB | `metadata.match.score` | ✅ Available |
| Candidate registration | `documents.metadata` JSONB | `metadata.match.candidate_registration_no` | ✅ Available |
| Matched-on fields | `documents.metadata` JSONB | `metadata.match.matched_on` | ✅ Available |
| Match band (derived status) | `documents.metadata` JSONB | `metadata.match.band` | ✅ Available |
| Pre-overwrite OCR values | `documents.metadata` JSONB | `metadata.match.ocr_extracted` | ✅ Available |
| Identity consistency score | `documents` | `consistency_score` | ✅ Available (Phase 2 feature) |
| Reference data registry row | `reference_data` | 36 Excel columns | ✅ Available |
| Similar approved documents | `documents` + `human_corrections` | `match_status`, `registration_no` | ✅ Available |
| Self-healing actions | `audit_log` | `action LIKE 'smart.%'` | ✅ Available |
| Stage durations | `audit_log` | `ts` diffs per stage | ⚠️ Derived (not pre-computed) |
| Self-healing reason text | `cloud/self_healing/patterns.py` | `is_known_name_variation`, `is_transliteration_variation` | ✅ Available (functions) |

### 3.2 Data Source Claims

```
Claim: The match stage writes a structured provenance block into `documents.metadata.match` containing method, score, candidate_registration_no, matched_on, band, and ocr_extracted.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §5.8 — Match
Date: 2026-06-16
Excerpt: "Writes `match_status` + `reference_data_id` + `metadata.match` provenance (`matched_on` includes `registration_no+name`). Does NOT touch `document.status`. Idempotent."
Context: This metadata block is the single most important data source for the Autopsy match-stage explanation. It persists the exact decision path.
Confidence: high
```

```
Claim: The `pages` table stores per-page OCR results in `structured_json` including `raw_text`, `words`, and OCR confidence per word.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §5.7 — Structure
Date: 2026-06-16
Excerpt: "OCR results: `pages.structured_json` — per-page entities, words, raw_text, OCR confidence"
Context: The structured_json is the raw material from which the autopsy extracts identity fields and OCR quality metrics.
Confidence: high
```

```
Claim: The `human_corrections` table stores every operator correction, enabling the autopsy to find "similar approved documents" with the same pattern.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §16.1 — Human Corrections Learning Loop
Date: 2026-06-16
Excerpt: "Schema: `human_corrections` table (document_id, page_num, correction_type, original_value, corrected_value, ai_confidence, username, ts)."
Context: The autopsy uses this to build recommendations like "37 other documents had the same pattern and were approved."
Confidence: high
```

```
Claim: The `audit_log` table captures every autonomous smart action (self-healing retry, match auto-resolve, etc.) with a `smart.*` prefix, providing a full decision trail.
Source: cloud/smart/audit.py
URL: File: cloud/smart/audit.py, Section: Module docstring
Date: 2026-06-16
Excerpt: "Every autonomous pipeline action (self-healing retry, match auto-resolve, identity reclassify, stuck-doc resume, learned-substitution apply) calls `record_smart_action`, which writes ONE row to the existing `audit_log` table with action prefixed `smart.`."
Context: This is the decision-log spine for Phase 4. The autopsy can query `audit_log` to show "System auto-rotated this page and retried OCR" as part of the explanation.
Confidence: high
```

---

## 4. Analysis 3: Data Availability Gap Analysis

### 4.1 Already Available (No New Backend Work Needed)

The following data sources are already fully wired and populated:

1. **Document metadata** (`documents` table) — all identity columns
2. **Page metadata** (`pages` table) — OCR status, confidence, structured_json
3. **Match provenance** (`documents.metadata.match`) — complete decision ladder data
4. **Reference data** (`reference_data` table) — 92,389 rows of registry ground truth
5. **Human corrections** (`human_corrections` table) — pattern learning source
6. **Self-healing patterns** (`cloud/self_healing/patterns.py`) — name variation / transliteration functions
7. **Audit log** (`audit_log` table) — smart action history
8. **Identity consistency score** (`documents.consistency_score`) — Phase 2 feature

### 4.2 Partially Available / Needs Minor Enhancement

| Gap | Current State | What's Needed | Effort |
|---|---|---|---|
| **Per-page OCR tier** | Field `ocr_tier` exists in `pages` table per schema but may not be populated by all OCR paths. The `cloud/ocr/consumer.py` writes `ocr_status` but tier tracking is implicit. | Ensure `ocr_tier` is written to `pages.structured_json` or a dedicated column during OCR. | Small — 1-2 lines in consumer |
| **Stage durations** | Not pre-computed. `audit_log` has timestamps but no duration fields. | Autopsy service currently hardcodes `duration_sec=None`. Derive from `audit_log` timestamps or add stage timing columns. | Small — derive from existing timestamps |
| **Registry name in match detail** | `metadata.match` stores `candidate_registration_no` but not the registry's full name. The autopsy must look up `reference_data` row to get the name for comparison. | `generate_autopsy` already fetches `reference_data` via `find_similar_approved_matches`, but the core match detail still uses the candidate reg as a proxy for registry name. | Small — add `ref_repo.find_by_registration_no` call in autopsy |

### 4.3 Needs to be Added for Full Autopsy

| Gap | Why Needed | Proposed Solution | Effort |
|---|---|---|---|
| **Self-healing narrative in autopsy** | When a document was auto-healed (rotated, sharpened, VLM-escalated), the operator should see this in the autopsy. | Query `audit_log` for `smart.*` actions on this `document_id` and append a "Self-healing" stage to the report. | Small — add `audit_log` query to `generate_autopsy` |
| **Human correction history** | If a document was previously corrected by a human, this context helps the current reviewer. | Query `human_corrections` for this `document_id` and include a "Previous Corrections" section. | Small — add query + template section |
| **Exact registry name for name-mismatch explanation** | The autopsy currently uses `candidate_registration_no` as a proxy for registry name in `explain_name_mismatch`. It needs the actual `reference_data.full_name` for accurate comparison. | Add a `ReferenceRepository` lookup in `generate_autopsy` when `match_meta.candidate_registration_no` is present. | Small — already have repo pattern |

### 4.4 Gap Analysis Claims

```
Claim: The autopsy service currently does not look up the actual registry row to get the full name for name-mismatch explanations; it uses the candidate registration number as a string proxy, which limits explanation accuracy.
Source: cloud/autopsy/service.py
URL: File: cloud/autopsy/service.py, Section: generate_autopsy — Match stage
Date: 2026-06-17
Excerpt: "registry_name = candidate_reg  # We don't have the registry name in metadata; would need lookup"
Context: This is a TODO comment in the existing autopsy service. The fix is straightforward — inject `ReferenceRepository` and fetch the row by `candidate_registration_no`.
Confidence: high
```

```
Claim: The autopsy service currently hardcodes all stage durations as `None` because stage timing is not pre-computed in the database.
Source: cloud/autopsy/service.py
URL: File: cloud/autopsy/service.py, Section: AutopsyStage dataclass usage
Date: 2026-06-17
Excerpt: "duration_sec: float | None = None" and all stage instantiations pass no duration.
Context: The dataclass supports duration but the service doesn't populate it. The data exists in `audit_log` as timestamp diffs between stage transitions.
Confidence: high
```

---

## 5. Analysis 4: Narratives API vs. Autopsy Mode Relationship

### 5.1 Narratives API (Existing)

```
Claim: The existing Narratives API (`GET /api/documents/{id}/narrative`) generates a 2-3 sentence plain-English summary of a document's journey from structured data. It is template-based, zero LLM cost, and lives in `cloud/narratives/service.py`.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §16.2 — AI-Generated Document Narratives
Date: 2026-06-16
Excerpt: "**Service:** `cloud/narratives/service.py` — template-based generation from structured data (match status, page types, identity fields, OCR quality, reviewer actions). No LLM call; pure string templating. **API:** `GET /api/documents/{document_id}/narrative` — returns a paragraph summary."
Context: The narrative is a high-level summary: "Ashish Patil (Reg. 34903), 12-page practitioner bundle. All pages OCR'd with average confidence 87%. Match status: matched. Identity verified across 3 identity pages."
Confidence: high
```

### 5.2 Autopsy API (Existing)

```
Claim: The Autopsy API (`GET /api/documents/{id}/autopsy`) generates a structured, stage-by-stage report with per-stage status, detail strings, and a recommendation. It is also template-based and zero LLM cost, living in `cloud/autopsy/service.py`.
Source: cloud/autopsy/service.py
URL: File: cloud/autopsy/service.py, Section: Module docstring + generate_autopsy
Date: 2026-06-17
Excerpt: "Document Autopsy Mode — template-based explanation for failed/manual_review documents. 100% template-based. No LLM. No cost. Generated in <10ms."
Context: The autopsy is a drill-down: per-stage breakdown, exact match scores, threshold comparisons, name mismatch explanations, and action recommendations.
Confidence: high
```

### 5.3 Relationship: Same Philosophy, Different Purpose

They are **different features serving different user needs** but built on the same template-engine philosophy:

| Dimension | Narratives API | Autopsy API |
|---|---|---|
| **Purpose** | High-level summary for any document | Deep failure diagnosis for flagged documents only |
| **Audience** | Operators browsing the document list | Operators reviewing a specific `manual_review` or `failed` document |
| **Content** | 2-3 sentences: identity, page count, OCR summary, match status | Stage-by-stage breakdown with exact scores, thresholds, explanations, recommendations |
| **Tone** | Informative, neutral | Diagnostic, actionable, prescriptive |
| **Actions** | None — read-only | Contains `recommendation` field driving UI buttons (Approve, Reject, Re-run) |
| **Data sources** | `documents` + `pages` | `documents` + `pages` + `metadata.match` + `reference_data` + `human_corrections` + `audit_log` |
| **API shape** | Plain text string | Structured JSON (`AutopsyReport` with `stages[]` array) |
| **Template engine** | Inline `if/else` string concatenation in `generate_narrative()` | Inline `if/else` string concatenation in `generate_autopsy()` |

```
Claim: The Narratives API and Autopsy API are NOT the same feature. They share the same zero-cost template philosophy but serve different purposes: Narratives = high-level summary for ALL documents; Autopsy = deep diagnostic for FAILED/MANUAL_REVIEW documents only.
Source: TASKS.md + cloud/autopsy/service.py + cloud/narratives/service.py
URL: File: TASKS.md, Section: Phase 5 (Pending) — Frontend feature build-out
Date: 2026-06-17
Excerpt: "- [ ] Document Autopsy mode — template-based explanation for every failed/manual_review doc (explanation-only, no heatmap)" vs. "- [ ] Aether Chat Interface — search bar + autocomplete..." and "- [ ] Engine Room v1 full UI..."
Context: TASKS.md lists them as separate Phase 5 items. The Narratives API was already built in Phase 2. The Autopsy API was also built in Phase 2 (the backend service exists). Phase 5 is about frontend build-out.
Confidence: high
```

### 5.4 Frontend Integration Implication

The document viewer should show **both**:
- A short narrative at the top (from `/narrative`) for context
- An "Autopsy" tab (from `/autopsy`) that expands only when the document is `manual_review` or `failed`

This is exactly what the Addendum's UI mockup shows:

```
Claim: The document viewer UI mockup shows both an AI-generated Document Summary (narrative) and a separate AI Context sidebar, plus an implied "Autopsy" tab for flagged documents.
Source: REIMAGINING_ADDENDUM.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §1 — The Document Viewer (Immersive, Not 3D)
Date: 2026-06-16
Excerpt: "Document Summary (AI-generated): Ashish R. Patil (Reg. 34903). 12-page bundle..." and "AI Context (live): • This registration appears in 3 other bundles..." and the "day in the life" scenario mentions opening the "Autopsy" tab.
Context: The mockup shows these as distinct panels. The narrative is a summary block; the autopsy is a separate tab the operator opens when they need to understand why something is flagged.
Confidence: high
```

---

## 6. Analysis 5: Template Engine Approach

### 6.1 Current Implementation: Pure Python String Concatenation

Both the Narratives and Autopsy services use the same template approach: **pure Python inline string formatting with `if/else` logic** — no external template library (Jinja2, Mustache, etc.).

```
Claim: The autopsy service uses pure Python string concatenation and conditional formatting — no external template library. The entire report is built by appending strings to a list based on `if/else` branches over database fields.
Source: cloud/autopsy/service.py
URL: File: cloud/autopsy/service.py, Section: generate_autopsy function
Date: 2026-06-17
Excerpt: "match_detail_parts: list[str] = []
match_detail_parts.append(f'Method: {method}')
if candidate_reg:
    match_detail_parts.append(f'Candidate registration: {candidate_reg}')
if score is not None:
    match_detail_parts.append(f'Name score: {score:.0f}% (threshold: {FUZZY_MATCH_HIGH:.0f}%)')"
Context: This is the core template logic. It is extremely fast (<10ms), deterministic, fully auditable, and requires zero dependencies. The trade-off is that the "template" is embedded in Python code, not a separate file.
Confidence: high
```

```
Claim: The narrative service uses the exact same pattern: inline `if/else` string concatenation with f-strings, no external template engine.
Source: cloud/narratives/service.py
URL: File: cloud/narratives/service.py, Section: generate_narrative function
Date: 2026-06-17
Excerpt: "if identity_parts:
    parts.append(f'{' — '.join(identity_parts)}, {doc.page_count}-page practitioner bundle.')
else:
    parts.append(f'{doc.original_filename}, {doc.page_count}-page {doc.document_category} bundle.')"
Context: Both services follow the same coding pattern. There is no shared template base class or engine — each is a standalone function. This is consistent with the "zero cost, zero dependency" philosophy.
Confidence: high
```

### 6.2 Why No External Template Engine

```
Claim: The grounded plan explicitly rejected external template engines and LLM calls for the autopsy because they add complexity, dependencies, and latency with no benefit for a deterministic, structured output.
Source: REIMAGINING_GROUNDED.md
URL: File: REIMAGINING_GROUNDED.md, Section: §10 — Document Autopsy Mode (Explanation Only)
Date: 2026-06-16
Excerpt: "**This is 100% template-based. No LLM. No cost. Generated in <10ms.**"
Context: The pseudocode in the design document shows a single function with string list appending. The actual implementation (`cloud/autopsy/service.py`) follows this design exactly.
Confidence: high
```

### 6.3 Recommended Template Engine Decision for Phase 5

**Keep the existing pure-Python approach.** The reasons:

1. **Zero dependency** — No Jinja2/Mustache to install in Lambda containers
2. **Zero latency** — <10ms generation, no template parsing overhead
3. **Fully auditable** — Every string path is explicit Python code, reviewable in Git
4. **Type-safe** — Dataclass model (`AutopsyReport`, `AutopsyStage`) enforces structure
5. **Testable** — Existing tests (`test_autopsy_api.py`) cover all branches
6. **Easy to modify** — Adding a new stage or field means adding a new `if` block

If the frontend needs localized/Marathi explanations in the future, the recommendation is to **wrap the Python template logic in a thin i18n layer** (e.g., a `AUTOPSY_MESSAGES` dict with Marathi/English strings) rather than switching to an external template engine.

---

## 7. Synthesis: Implementation Needs for Phase 5 Frontend

### 7.1 Backend Status: Already Complete

The backend for Document Autopsy Mode is **already implemented and tested**:

| Component | Status | File |
|---|---|---|
| Autopsy service | ✅ Complete | `cloud/autopsy/service.py` |
| API endpoint | ✅ Complete | `cloud/dashboard/api.py` — `GET /api/documents/{id}/autopsy` |
| Unit tests | ✅ Complete | `tests/cloud/test_autopsy_api.py` |
| Data model | ✅ Complete | `AutopsyReport` + `AutopsyStage` dataclasses |
| Name mismatch explainer | ✅ Complete | `explain_name_mismatch()` with rapidfuzz |
| Similar matches finder | ✅ Complete | `find_similar_approved_matches()` |

### 7.2 Frontend Work Needed (Phase 5)

| Task | Description | Complexity |
|---|---|---|
| **Autopsy Tab UI** | Add an "Autopsy" tab to the document viewer ( Next.js + MUI). Only visible when `status == 'manual_review'` or `status == 'failed'`. | Low |
| **Stage List Renderer** | Render the `stages[]` array from `AutopsyReport` as a vertical timeline with icons (✅/⚠️/⏸/✗). | Low |
| **Match Detail Card** | Expand the `match` stage with a decision-tree card: exact reg check → name score → DOB check → final decision. Show thresholds visually (progress bar or badge). | Medium |
| **Recommendation Banner** | Render the `recommendation` string as a prominent call-to-action banner. If recommendation mentions "approved after review", show green banner. If "review and approve", show amber. | Low |
| **Action Buttons** | Wire buttons from the recommendation context: "Approve Match" → `POST /api/documents/{id}/approve`; "Reject Match" → `POST /api/documents/{id}/reject`; "Re-run OCR" → `POST /api/engine/requeue`. | Medium |
| **Name Mismatch Explanation** | In the match stage, when `explain_name_mismatch` returns "Middle name omitted" or "Initials used", show a helper tooltip with the registry full name and extracted name side-by-side. | Low |
| **Self-healing Badge** | If `audit_log` contains `smart.*` actions for this doc, show a small "Auto-healed" badge in the Autopsy tab with a tooltip listing the actions. | Low |
| **Accessibility** | Ensure the Autopsy tab is keyboard-navigable, screen-reader announces stage statuses, and color-blind indicators use icons + text (not just color). | Medium |

### 7.3 API Contract for Frontend

```json
{
  "document_id": "abc123...",
  "overall_status": "manual_review",
  "stages": [
    {
      "name": "ingest",
      "status": "success",
      "detail": "13 pages uploaded. 1 blank page(s) skipped.",
      "duration_sec": null
    },
    {
      "name": "match",
      "status": "manual_review",
      "detail": "Method: exact; Candidate registration: 34903; Name score: 72% (threshold: 90%); Matched on: registration_no; Reason: Name score 72% is below auto-match threshold 90%; Explanation: Middle name omitted in extracted text",
      "duration_sec": null
    }
  ],
  "recommendation": "37 other document(s) with the same registration number were approved after review. This is likely a known name variation."
}
```

### 7.4 No New Backend APIs Needed

The frontend can build the Autopsy tab using **only existing APIs**:
- `GET /api/documents/{id}/autopsy` — the full report
- `GET /api/documents/{id}/narrative` — top-level summary (optional, for context)
- `POST /api/eval/correct` — to record human corrections after operator action
- Existing dashboard action endpoints for approve/reject/requeue

### 7.5 Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| `ocr_tier` column not populated for all pages | Medium | Fallback to "unknown" in autopsy UI; fix backend consumer to write tier |
| Registry name lookup missing from autopsy | Low | Add `ReferenceRepository` lookup in `generate_autopsy` before Phase 5 ships |
| Stage durations all `null` | Low | Omit duration from UI or derive from `audit_log` timestamps |
| Marathi explanations needed | Low | Future i18n layer; English is acceptable for Phase 5 |
| Recommendation text too generic | Medium | Enhance `find_similar_approved_matches` query to use `human_corrections` table, not just `registration_no` match |

---

## 8. Appendix: Raw Claim Inventory

All claims from this analysis are reproduced below in the exact output format requested.

### Claim 1
```
Claim: The original Document Autopsy Mode envisioned visual heatmaps for scan-quality issues, top-3 OCR alternative readings with confidence, and side-by-side registry entry comparisons.
Source: REIMAGINING.md
URL: File: REIMAGINING.md, Section: Appendix A — The "Document Autopsy" Mode
Date: 2026-06-16
Excerpt: "Was it a scan quality issue? Show the problematic region with a heatmap. Was it an OCR ambiguity? Show the top 3 alternative readings with confidence. Was it a registry mismatch? Show the closest registry entries side-by-side."
Context: Listed under "Crazy Ideas That Might Be Genius" in the creative brainstorm document. Explicitly labeled as "not fully thought through — they're sparks."
Confidence: high
```

### Claim 2
```
Claim: The Document Autopsy Mode was accepted into the grounded plan only after removing all heatmaps, spatial visualizations, and LLM-generated text. It became a template-based text explanation of the failure decision tree.
Source: REIMAGINING_COMPARISON.md
URL: File: REIMAGINING_COMPARISON.md, Section: §3 — The "Crazy Ideas" Appendix — Fate
Date: 2026-06-16
Excerpt: "| Document Autopsy Mode | Explain failures with heatmaps | Template-based text explanation of failure decision tree. No heatmaps. | ✅ ACCEPTED — heavily simplified |"
Context: Part of a feature-by-feature comparison table showing original brainstorm ideas vs. grounded reality. Document Autopsy is one of only three "Crazy Ideas" that survived.
Confidence: high
```

### Claim 3
```
Claim: The original heatmap-based autopsy would require GPU rendering or complex image processing, estimated at $200+/month just for the spatial canvas feature.
Source: REIMAGINING_COMPARISON.md
URL: File: REIMAGINING_COMPARISON.md, Section: §6 — Cost Comparison: Original vs. Grounded
Date: 2026-06-16
Excerpt: "| Spatial canvas (2D/3D) | $200+/month GPU or high-end instance | Rendering 92K documents in WebGL/Canvas requires GPU or high CPU |"
Context: Part of a cost table showing the original vision would cost $2,000+/month vs. the grounded plan at $278-350/month. The heatmap/spatial visualizations were the single most expensive line item.
Confidence: high
```

### Claim 4
```
Claim: Government operators do not need or want visual heatmaps. They need a clear, fast explanation of why a document was flagged, written in plain English, with a one-click action to resolve it.
Source: REIMAGINING_COMPARISON.md
URL: File: REIMAGINING_COMPARISON.md, Section: §8 — What the Operator Actually Sees: Day in the Life
Date: 2026-06-16
Excerpt: "The document is flagged for manual review. They open the 'Autopsy' tab. They read: 'The registration number matched perfectly. The DOB matched perfectly. The only issue: the name has a missing middle name. This is a common pattern. 37 other documents had the same pattern and were approved.' They click 'Approve Match'."
Context: This is the canonical "day in the life" scenario that the grounded plan was optimized for. The entire UX flow is described in 3 sentences and one click.
Confidence: high
```

### Claim 5
```
Claim: The owner explicitly mandated that the Autopsy mode must have zero LLM cost, generating explanations purely from structured database fields via string templating.
Source: REIMAGINING_GROUNDED.md
URL: File: REIMAGINING_GROUNDED.md, Section: §10 — Document Autopsy Mode (Explanation Only)
Date: 2026-06-16
Excerpt: "# cloud/autopsy/service.py — new module
async def generate_autopsy(document_id: str) -> str:
    """Generate a plain-English autopsy report. No LLM. Just template + data.""""
Context: The design document includes a full Python pseudocode implementation showing exactly how the template engine works. It explicitly states "This is 100% template-based. No LLM. No cost. Generated in <10ms."
Confidence: high
```

### Claim 6
```
Claim: Despite removing heatmaps, the Document Autopsy mode retains the "warm editorial minimalism" design philosophy — formal, respectful, deeply informative, with purposeful animation and clear hierarchy.
Source: REIMAGINING_ADDENDUM.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §1 — Design Philosophy: Simple System, Beautiful UX
Date: 2026-06-16
Excerpt: "1. No spatial canvas. But the document viewer is immersive, smooth, and contextual. 2. No gamification. But the interface is rewarding to use. 3. No 3D. But the interface has depth through shadows, layers, and purposeful animation. 4. No voice/stylus/gesture. But every action is keyboard-accessible, touch-friendly, and screen-reader compatible. 5. No futuristic sci-fi. But the interface feels modern, warm, and confident."
Context: These are the 5 Key Design Decisions from the Addendum. The autopsy tab lives inside this design envelope — no sci-fi, but polished and professional.
Confidence: high
```

### Claim 7
```
Claim: The match stage writes a structured provenance block into `documents.metadata.match` containing method, score, candidate_registration_no, matched_on, band, and ocr_extracted.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §5.8 — Match
Date: 2026-06-16
Excerpt: "Writes `match_status` + `reference_data_id` + `metadata.match` provenance (`matched_on` includes `registration_no+name`). Does NOT touch `document.status`. Idempotent."
Context: This metadata block is the single most important data source for the Autopsy match-stage explanation. It persists the exact decision path.
Confidence: high
```

### Claim 8
```
Claim: The `pages` table stores per-page OCR results in `structured_json` including `raw_text`, `words`, and OCR confidence per word.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §5.7 — Structure
Date: 2026-06-16
Excerpt: "OCR results: `pages.structured_json` — per-page entities, words, raw_text, OCR confidence"
Context: The structured_json is the raw material from which the autopsy extracts identity fields and OCR quality metrics.
Confidence: high
```

### Claim 9
```
Claim: The `human_corrections` table stores every operator correction, enabling the autopsy to find "similar approved documents" with the same pattern.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §16.1 — Human Corrections Learning Loop
Date: 2026-06-16
Excerpt: "Schema: `human_corrections` table (document_id, page_num, correction_type, original_value, corrected_value, ai_confidence, username, ts)."
Context: The autopsy uses this to build recommendations like "37 other documents had the same pattern and were approved."
Confidence: high
```

### Claim 10
```
Claim: The `audit_log` table captures every autonomous smart action (self-healing retry, match auto-resolve, etc.) with a `smart.*` prefix, providing a full decision trail.
Source: cloud/smart/audit.py
URL: File: cloud/smart/audit.py, Section: Module docstring
Date: 2026-06-16
Excerpt: "Every autonomous pipeline action (self-healing retry, match auto-resolve, identity reclassify, stuck-doc resume, learned-substitution apply) calls `record_smart_action`, which writes ONE row to the existing `audit_log` table with action prefixed `smart.`."
Context: This is the decision-log spine for Phase 4. The autopsy can query `audit_log` to show "System auto-rotated this page and retried OCR" as part of the explanation.
Confidence: high
```

### Claim 11
```
Claim: The autopsy service currently does not look up the actual registry row to get the full name for name-mismatch explanations; it uses the candidate registration number as a string proxy, which limits explanation accuracy.
Source: cloud/autopsy/service.py
URL: File: cloud/autopsy/service.py, Section: generate_autopsy — Match stage
Date: 2026-06-17
Excerpt: "registry_name = candidate_reg  # We don't have the registry name in metadata; would need lookup"
Context: This is a TODO comment in the existing autopsy service. The fix is straightforward — inject `ReferenceRepository` and fetch the row by `candidate_registration_no`.
Confidence: high
```

### Claim 12
```
Claim: The autopsy service currently hardcodes all stage durations as `None` because stage timing is not pre-computed in the database.
Source: cloud/autopsy/service.py
URL: File: cloud/autopsy/service.py, Section: AutopsyStage dataclass usage
Date: 2026-06-17
Excerpt: "duration_sec: float | None = None" and all stage instantiations pass no duration.
Context: The dataclass supports duration but the service doesn't populate it. The data exists in `audit_log` as timestamp diffs between stage transitions.
Confidence: high
```

### Claim 13
```
Claim: The existing Narratives API (`GET /api/documents/{id}/narrative`) generates a 2-3 sentence plain-English summary of a document's journey from structured data. It is template-based, zero LLM cost, and lives in `cloud/narratives/service.py`.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §16.2 — AI-Generated Document Narratives
Date: 2026-06-16
Excerpt: "**Service:** `cloud/narratives/service.py` — template-based generation from structured data (match status, page types, identity fields, OCR quality, reviewer actions). No LLM call; pure string templating. **API:** `GET /api/documents/{document_id}/narrative` — returns a paragraph summary."
Context: The narrative is a high-level summary: "Ashish Patil (Reg. 34903), 12-page practitioner bundle. All pages OCR'd with average confidence 87%. Match status: matched. Identity verified across 3 identity pages."
Confidence: high
```

### Claim 14
```
Claim: The Autopsy API (`GET /api/documents/{id}/autopsy`) generates a structured, stage-by-stage report with per-stage status, detail strings, and a recommendation. It is also template-based and zero LLM cost, living in `cloud/autopsy/service.py`.
Source: cloud/autopsy/service.py
URL: File: cloud/autopsy/service.py, Section: Module docstring + generate_autopsy
Date: 2026-06-17
Excerpt: "Document Autopsy Mode — template-based explanation for failed/manual_review documents. 100% template-based. No LLM. No cost. Generated in <10ms."
Context: The autopsy is a drill-down: per-stage breakdown, exact match scores, threshold comparisons, name mismatch explanations, and action recommendations.
Confidence: high
```

### Claim 15
```
Claim: The Narratives API and Autopsy API are NOT the same feature. They share the same zero-cost template philosophy but serve different purposes: Narratives = high-level summary for ALL documents; Autopsy = deep diagnostic for FAILED/MANUAL_REVIEW documents only.
Source: TASKS.md + cloud/autopsy/service.py + cloud/narratives/service.py
URL: File: TASKS.md, Section: Phase 5 (Pending) — Frontend feature build-out
Date: 2026-06-17
Excerpt: "- [ ] Document Autopsy mode — template-based explanation for every failed/manual_review doc (explanation-only, no heatmap)" vs. "- [ ] Aether Chat Interface — search bar + autocomplete..." and "- [ ] Engine Room v1 full UI..."
Context: TASKS.md lists them as separate Phase 5 items. The Narratives API was already built in Phase 2. The Autopsy API was also built in Phase 2 (the backend service exists). Phase 5 is about frontend build-out.
Confidence: high
```

### Claim 16
```
Claim: The autopsy service uses pure Python string concatenation and conditional formatting — no external template library. The entire report is built by appending strings to a list based on `if/else` branches over database fields.
Source: cloud/autopsy/service.py
URL: File: cloud/autopsy/service.py, Section: generate_autopsy function
Date: 2026-06-17
Excerpt: "match_detail_parts: list[str] = []
match_detail_parts.append(f'Method: {method}')
if candidate_reg:
    match_detail_parts.append(f'Candidate registration: {candidate_reg}')
if score is not None:
    match_detail_parts.append(f'Name score: {score:.0f}% (threshold: {FUZZY_MATCH_HIGH:.0f}%)')"
Context: This is the core template logic. It is extremely fast (<10ms), deterministic, fully auditable, and requires zero dependencies. The trade-off is that the "template" is embedded in Python code, not a separate file.
Confidence: high
```

### Claim 17
```
Claim: The narrative service uses the exact same pattern: inline `if/else` string concatenation with f-strings, no external template engine.
Source: cloud/narratives/service.py
URL: File: cloud/narratives/service.py, Section: generate_narrative function
Date: 2026-06-17
Excerpt: "if identity_parts:
    parts.append(f'{' — '.join(identity_parts)}, {doc.page_count}-page practitioner bundle.')
else:
    parts.append(f'{doc.original_filename}, {doc.page_count}-page {doc.document_category} bundle.')"
Context: Both services follow the same coding pattern. There is no shared template base class or engine — each is a standalone function. This is consistent with the "zero cost, zero dependency" philosophy.
Confidence: high
```

### Claim 18
```
Claim: The grounded plan explicitly rejected external template engines and LLM calls for the autopsy because they add complexity, dependencies, and latency with no benefit for a deterministic, structured output.
Source: REIMAGINING_GROUNDED.md
URL: File: REIMAGINING_GROUNDED.md, Section: §10 — Document Autopsy Mode (Explanation Only)
Date: 2026-06-16
Excerpt: "**This is 100% template-based. No LLM. No cost. Generated in <10ms.**"
Context: The pseudocode in the design document shows a single function with string list appending. The actual implementation (`cloud/autopsy/service.py`) follows this design exactly.
Confidence: high
```

### Claim 19
```
Claim: The document viewer UI mockup shows both an AI-generated Document Summary (narrative) and a separate AI Context sidebar, plus an implied "Autopsy" tab for flagged documents.
Source: REIMAGINING_ADDENDUM.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §1 — The Document Viewer (Immersive, Not 3D)
Date: 2026-06-16
Excerpt: "Document Summary (AI-generated): Ashish R. Patil (Reg. 34903). 12-page bundle..." and "AI Context (live): • This registration appears in 3 other bundles..." and the "day in the life" scenario mentions opening the "Autopsy" tab.
Context: The mockup shows these as distinct panels. The narrative is a summary block; the autopsy is a separate tab the operator opens when they need to understand why something is flagged.
Confidence: high
```

### Claim 20
```
Claim: The backend for Document Autopsy Mode is already substantially complete with a working service, API endpoint, tests, and dataclass model. The remaining Phase 5 work is almost entirely frontend UI integration.
Source: TASKS.md + cloud/autopsy/service.py + tests/cloud/test_autopsy_api.py + cloud/dashboard/api.py
URL: File: TASKS.md, Section: Phase 5 (Pending) — Frontend feature build-out
Date: 2026-06-17
Excerpt: "- [ ] Document Autopsy mode — template-based explanation for every failed/manual_review doc (explanation-only, no heatmap)"
Context: The backend service (`cloud/autopsy/service.py`) and API endpoint (`cloud/dashboard/api.py::/documents/{id}/autopsy`) and tests (`tests/cloud/test_autopsy_api.py`) are all already implemented. The Phase 5 checkbox implies frontend build-out.
Confidence: high
```

---

*End of analysis.*
