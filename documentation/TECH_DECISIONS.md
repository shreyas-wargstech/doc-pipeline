# Technology Decisions, Thresholds & Trade-offs

> Why each tool was chosen, what alternatives exist, and what the trade-offs are.

---

## Table of Contents

1. [Language & Runtime](#1-language--runtime)
2. [Package Management](#2-package-management)
3. [Data Persistence](#3-data-persistence)
4. [Object Storage](#4-object-storage)
5. [Vector Database](#5-vector-database)
6. [Graph Database](#6-graph-database)
7. [Embedding Model](#7-embedding-model)
8. [OCR Engine](#8-ocr-engine)
9. [Image Preprocessing](#9-image-preprocessing)
10. [PDF Handling](#10-pdf-handling)
11. [ORM / Database Layer](#11-orm--database-layer)
12. [Async HTTP / API](#12-async-http--api)
13. [Fuzzy Matching](#13-fuzzy-matching)
14. [Structured Logging](#14-structured-logging)
15. [Configuration](#15-configuration)
16. [Data Validation](#16-data-validation)
17. [Thresholds Reference](#17-thresholds-reference)
18. [Deferred / Pending Decisions](#18-deferred--pending-decisions)
19. [Operations / Control Dashboard (planned)](#19-operations--control-dashboard-planned)
20. [Retrieval Strategy — Lean Ownership Propagation](#20-retrieval-strategy--lean-ownership-propagation)

---

## 1. Language & Runtime

### Python 3.11+ (pipeline core)

**Chosen because:**
- Native `asyncio` is mature and well-supported by all stack libraries (asyncpg, aioboto3, qdrant-client, neo4j-driver).
- ML/CV ecosystem lives here: Tesseract bindings, OpenCV, sentence-transformers, spaCy, PyMuPDF.
- Type hint + Pydantic v2 combination gives near-TypeScript-level safety for I/O contracts.

**Alternatives considered:**

| Option | Why not |
|---|---|
| Python 3.10 | Missing `match` statement syntax sugar; `asyncio` task groups added in 3.11 |
| Node.js for pipeline | No mature Tesseract / OpenCV / sentence-transformers bindings; ML ecosystem is Python |
| Java / Go | No justification given team expertise and ML library availability |

**Confirmed working on:** Python 3.13.7, Windows (dev) + Linux (prod target).

---

### Node.js + TypeScript (client API layer)

**Chosen because:**
- Thin HTTP adapter between external callers and the Python FastAPI service.
- TypeScript + Zod gives compile-time + runtime validation of API contracts.
- Wide familiarity for web-facing API development.

---

## 2. Package Management

### `uv`

**Chosen because:**
- 10–100× faster than pip for dependency resolution.
- Single tool for venv creation + locking + sync (`uv sync --extra dev`).
- Compatible with standard `pyproject.toml`.

**Alternatives considered:**

| Option | Why not |
|---|---|
| pip + requirements.txt | No locking, slow, error-prone on reinstalls |
| poetry | Slower resolver; non-standard build backend sometimes causes issues |
| conda | Overkill; heavier; mixes package management with env management |

---

## 3. Data Persistence

### PostgreSQL 16

**Chosen because:**
- JSONB with GIN indexing allows hybrid structured + semi-structured queries on the same table (`reference_data.fields_norm`, `pages.structured_json`).
- Native `ON CONFLICT DO UPDATE` (upsert) makes idempotency easy to implement.
- `asyncpg` driver is the fastest async Postgres driver available; pairs well with SQLAlchemy 2.0 async.
- Mature, battle-tested; AWS RDS Aurora Postgres is the prod path.

**Alternatives considered:**

| Option | Why not |
|---|---|
| MySQL / MariaDB | No native JSONB; GIN indexes not available; weaker UPSERT semantics |
| MongoDB | Schemaless would lose the FK discipline needed for match_status tracking |
| SQLite | Not suitable for async concurrent writes; no prod story |
| DynamoDB | No JSONB-style indexed queries; more expensive for relational patterns |

**Key schema decisions:**
- `fields_norm JSONB` + GIN index on `reference_data` → O(1) lookup on any normalised field value.
- `structured_json JSONB` on `pages` → flexible LLM output without schema migrations per document type.
- `document_category ENUM` → enforces valid states at DB level, not just application level.

---

## 4. Object Storage

### S3 (AWS) / MinIO (dev)

**Chosen because:**
- Natural trigger mechanism: S3 `ObjectCreated` event on `manifest.json` drives the cloud pipeline without polling.
- Immutable, durable blob store for original PDFs + page images.
- `put_if_absent` pattern prevents re-upload of identical content (idempotency without extra DB lookups).
- MinIO is API-compatible with S3 — same code, different `endpoint_url`.

**Layout:**
```
documents/<sha256_doc_id>/
  original.pdf
  manifest.json
  pages/
    page_001.png
    page_002.png
    ...
```

**Why manifest.json uploaded last:** Acts as an atomic "ready" signal. If the upload is interrupted partway, no trigger fires and no partial state is processed.

---

## 5. Vector Database

### Qdrant

**Chosen because:**
- Native support for **payload filtering** alongside vector similarity — critical for the retrieval flow where Neo4j returns a candidate `document_id` set and Qdrant re-ranks within it.
- Rust-based; fast and memory-efficient compared to Python-native alternatives.
- `qdrant-client` has a clean async Python API.
- Docker image is lightweight and easy to run locally.

**Alternatives considered:**

| Option | Why not |
|---|---|
| Pinecone | Managed only; no local dev; cost at scale |
| Weaviate | Heavier footprint; more opinionated schema |
| pgvector | Reasonable alternative, but less performant at scale; indexing less mature |
| ChromaDB | Embedded/single-node focus; less suited for production deployment |
| FAISS | No built-in server; no payload filtering without custom wrapping |

**Collection config:**
```
Collection:  document_pages
Vector size: 384
Distance:    Cosine
```

**Why Cosine distance:** Semantic similarity for text is about direction of the embedding vector (topic alignment), not magnitude. Cosine normalises out document length effects.

**What gets embedded (revised 2026-06-10):** only **identity pages** (`app_cover`/`application_form`), not every page. Primary retrieval is structured (`owner × page_type` in Postgres, §20); Qdrant is the light semantic backup over the applicant-data text that anchors a bundle. Non-identity pages (Aadhaar, certs, receipts) are never transcribed, so there is no per-page text to embed — by design (§20).

---

## 6. Graph Database

### Neo4j 5 (with APOC)

**Chosen because:**
- Graph traversal is the natural data model for the retrieval query: *Person → BELONGS_TO → Document → HAS_PAGE → Page → MENTIONS → Entity*.
- `MERGE` semantics make all writes idempotent without application-level checks.
- APOC procedures needed for advanced graph algorithms (future: entity deduplication, community detection on related practitioners).
- Cypher is expressive enough to handle the hybrid structured filter + graph walk in one query.

**Alternatives considered:**

| Option | Why not |
|---|---|
| Amazon Neptune | Managed but expensive; no good local dev equivalent |
| TigerGraph | Steeper learning curve; less Python ecosystem support |
| ArangoDB | Multi-model is interesting but adds complexity; Cypher ecosystem larger |
| Pure Postgres (graph via JOINs) | Painful for multi-hop traversal; no native graph algorithms |

**Key constraints:**
- `Document.document_id` UNIQUE — prevents duplicate document nodes.
- `Page.page_id` UNIQUE — `<document_id>:<page_num>` format.
- `Person.registration_no` UNIQUE — replaces the fragile `(name, dob)` key (OCR frequently misreads dates; `registration_no` is printed clearly and QR-encoded).
- Index on `(Entity.type, Entity.value)` — speeds up entity lookup queries.

---

## 7. Embedding Model

### `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions)

**Chosen because:**
- **Multilingual:** Trained on 50+ languages including Hindi and Marathi — the two non-English languages present in the documents. The original `all-MiniLM-L6-v2` (English-only) was replaced specifically for this reason.
- **384-dim:** Small enough to be fast on CPU; large enough for good semantic resolution. Qdrant collection was designed at 384-dim from the start so the model switch required no re-indexing.
- **`paraphrase` variant:** Better at matching semantically equivalent phrasings (e.g., "Dr Ashish Patil" ↔ "Ashish Ramesh Patil") than the `sentence` variants.

**Alternatives considered:**

| Model | Dims | Multilingual | Why not |
|---|---|---|---|
| `all-MiniLM-L6-v2` | 384 | ✗ (English only) | Fails on Marathi/Hindi tokens |
| `all-MiniLM-L12-v2` | 384 | ✗ | Same issue |
| `LaBSE` | 768 | ✓ | 2× vector size = 2× storage + 2× search cost; would require Qdrant re-init |
| `text-embedding-3-small` (OpenAI) | 1536 | ✓ | API cost; network dependency; latency; data privacy concern for government docs |
| `multilingual-e5-large` | 1024 | ✓ | Overkill at 1024 dims for this use case; larger install |

**Note:** Changing the model after data is indexed requires a full re-embed and re-upsert of all vectors. The 384-dim choice was made early and locked to avoid this.

---

## 8. OCR Engine — Proactive Tier Routing

> **Revised 2026-05-26 (strategy) / 2026-06-06 (impl).** Replaces the old
> reactive confidence-cascade (Tesseract → Qwen/Gemma VLM on low confidence).
> The cascade was abandoned because Tesseract is bad at handwriting and can
> emit *confident garbage* that slips the 70 gate — so a reactive net never
> fires. We now **classify first, then route** to the right engine up front.
>
> **Revised 2026-06-09 — GCV removed, ladder collapsed to 2 tiers
> `(tesseract, vlm)`.** Google Cloud Vision (T2) is dropped: its per-word
> confidence + bounding boxes were the only thing distinguishing it from the
> VLM tier, and nothing downstream consumes them (Structure reads `raw_text`).
> The OpenRouter VLM (Gemini 2.5 Flash, formerly T3) is promoted to the sole
> cloud tier, renamed model-agnostically to `vlm`. Result: one cloud credential
> (`OPENROUTER_API_KEY`) covers all cloud OCR; the GCP service-account
> dependency is gone. The confidence-net (70) survives on the meaningful
> Tesseract→VLM hop. A two-VLM ladder escalating on a fixed conf prior carried
> no signal, hence the collapse.
>
> **Revised 2026-06-10 — identity-scoped transcription (lean retrieval).**
> Only **identity pages** (coarse `page_type` `cover`/`form`) now get the full
> Tesseract→VLM ladder. Every other page is **Tesseract-only** (no paid VLM
> transcription); its fine `page_type` is assigned by a cheap keyword typer
> (`cloud/ocr/page_type.py`) that escalates to a VLM **classify** call (a single
> label, NOT a transcription) only when keyword confidence < 0.5. Rationale +
> the full retrieval rethink it serves are in **§20**.

### Routing model

Triage (NAS-side, see §9) labels each page with a `content_type`
(`typed | handwritten | unknown`) and a `language_hint`
(`latin | devanagari | mixed | unknown`). `cloud/ocr/router.py` picks the
**starting tier** from `content_type`, then escalates on failure / low
confidence. The 70-confidence gate is **retained as a safety net** under the
proactive router (catches typed pages Tesseract mangles).

| Tier | Engine | Handles | Status |
|---|---|---|---|
| **T1** | Tesseract `eng+mar+hin` (`pytesseract`) | Typed / printed pages | ✅ done |
| **T2** | VLM via OpenRouter (`google/gemini-2.5-flash`, tier `vlm`) | Handwriting (English + Devanagari) + messy scans + low-conf escalation | ✅ done |

Escalation is by **difficulty (typed → everything-else)**: typed pages start at
Tesseract and escalate to the VLM if the 70-net fires; handwritten pages start
directly at the VLM. The VLM is multilingual, so handwritten-English and
handwritten-Devanagari go through the same call — no per-script fan-out.

### T1 — Tesseract (via `pytesseract`)

- `image_to_data(output_type=DICT)` returns per-word confidence + bounding
  boxes — feeds the confidence-net gate.
- `eng+mar+hin` language packs; handles Devanagari reasonably on *typed* text.
- Open source, no API cost, runs locally on NAS / in Lambda.

### T2 — VLM transcription (via OpenRouter) — `cloud/ocr/tiers/vlm.py`

- The sole cloud tier (was T3 "Gemini VLM" before the 2026-06-09 collapse).
  Reads the page image directly (no character segmentation); covers handwritten
  English + Devanagari and messy scans in one multilingual call.
- **Transport = OpenRouter**, reached with the `openai` SDK pointed at
  `OPENROUTER_BASE_URL` (OpenAI-compatible Chat Completions). The user runs on
  OpenRouter, so we go through it rather than Google AI Studio direct or Vertex
  AI. Model id `google/gemini-2.5-flash` (OpenRouter-namespaced); tier name is
  model-agnostic (`vlm`) so the model can be A/B-swapped without renaming.
- Auth via `OPENROUTER_API_KEY` → `Settings.openrouter_api_key`; absent →
  `TierNotImplemented` (graceful degradation — typed-only pages still run on
  Tesseract). Image sent as a base64 `image_url` data-URL. Sync call offloaded
  via `anyio.to_thread.run_sync`.
- VLMs emit no per-word confidence: words get a fixed `_CONF_PRIOR = 85.0`
  (above the 70 net) + `bbox=(0,0,0,0)`. An unavailable VLM on a handwritten
  page fails cleanly → `manual_review`; there is **no** fall-back to Tesseract
  (that would reintroduce the confident-garbage the proactive ladder avoids).

**Alternatives considered / rejected:**

| Option | Why not |
|---|---|
| **AWS Textract** | **Rejected** — no Devanagari (only eng/spa/ger/fre/ita/por; handwriting English-only). |
| **Qwen / Gemma local VLM** | **Superseded** — was the old reactive fallback; replaced by the Tesseract (T1) + OpenRouter VLM (T2) tiers. |
| **Google Cloud Vision** (`DOCUMENT_TEXT_DETECTION`) | **Removed 2026-06-09** — was T2 for handwriting; dropped when the ladder collapsed to `(tesseract, vlm)`. Its per-word conf/bboxes were unused downstream, and it required a second cloud credential (GCP service account). The OpenRouter VLM covers handwritten Devanagari. |
| PaddleOCR | Good multilingual support but heavier setup; T1+T2 cover the need. |
| docTR | Strong on printed text; weaker on mixed-script Devanagari. |
| EasyOCR | Weaker on dense multi-column layouts; slower than Tesseract. |

---

## 9. Image Preprocessing

### OpenCV + Pillow + scikit-image

**Chosen because:**
- Industry standard for CV preprocessing pipelines.
- Each step is independently controllable (all toggleable via config flags).
- Well-documented failure modes for scanned document enhancement.

**Preprocessing pipeline:**

| Step | Method | Why |
|---|---|---|
| Greyscale | `cv2.cvtColor` | Reduces noise channels; OCR engines perform better on greyscale |
| Denoise | `cv2.fastNlMeansDenoising` | Scanner noise (salt-and-pepper) causes false character detection |
| Deskew | Hough transform or projection profile | Scanned documents are frequently ±2–5° off-axis; Tesseract accuracy drops sharply past ±3° |
| Rotation correction | 0°/90°/180°/270° detection | Upside-down or sideways scans occur in bulk batches |
| Adaptive threshold | Otsu or Sauvola | Handles uneven illumination (page edges darker, coffee stains, etc.) |

**Why Sauvola over Otsu:** Sauvola uses a local window mean and variance; better for pages with uneven lighting gradients (common in bulk-scanned government documents). Otsu is global and faster but fails on shadowed edges.

---

## 10. PDF Handling

### PyMuPDF (`fitz`) — primary

**Chosen because:**
- Fastest PDF rasterisation library in Python.
- Handles malformed/corrupted PDFs better than most alternatives.
- Can extract text layer directly (used for cover-page QR/text pre-check before full OCR).

### `pdf2image` — fallback

**Used for:** Pages where `fitz` rasterisation produces artifacts. Wraps `pdftoppm` (Poppler) internally.

**Alternatives considered:**

| Option | Why not |
|---|---|
| pdfplumber | Good for text extraction; poor for image rasterisation quality |
| PDFMiner | Text only; no image support |
| pikepdf | Strong for PDF manipulation (merging, splitting); not a rasteriser |

---

## 11. ORM / Database Layer

### SQLAlchemy 2.0 async + asyncpg

**Chosen because:**
- SQLAlchemy 2.0 introduced a clean async API (`AsyncSession`, `async with session_scope()`).
- `asyncpg` is the fastest async Postgres driver; significantly faster than `psycopg2` in I/O-bound workloads.
- `ON CONFLICT DO UPDATE` (upsert) is expressible via `insert(...).on_conflict_do_update(...)` without raw SQL.

**Why not an ORM like Django ORM or Tortoise ORM:**
- SQLAlchemy Core (used here alongside ORM) gives fine-grained control over upsert logic needed for idempotency.
- Django ORM carries too much web-framework baggage; not appropriate for a pipeline service.

---

## 12. Async HTTP / API

### FastAPI

**Chosen because:**
- Native async; pairs naturally with async SQLAlchemy, aioboto3, qdrant-client.
- Auto-generates OpenAPI docs.
- Pydantic v2 models work directly as request/response schemas.

### `aioboto3`

- Async wrapper around `boto3`; required for non-blocking S3 operations inside async pipeline stages.

---

## 13. Fuzzy Matching

### `rapidfuzz`

**Chosen because:**
- Significantly faster than `fuzzywuzzy` (C extension; no Python loops).
- Multiple algorithms available: `ratio`, `partial_ratio`, `token_sort_ratio`, `WRatio` — important for name matching where word order varies (e.g., "Patil Ashish" vs "Ashish Patil").
- Handles Unicode correctly (important for Devanagari transliterated names).

**Use case in pipeline:** When OCR confidence for a token is below 70, the surrounding extracted context is fuzzy-matched against `reference_data.fields_norm` to attempt a substitution.

**Alternatives considered:**

| Option | Why not |
|---|---|
| `fuzzywuzzy` | Slower pure-Python; `rapidfuzz` is its maintained, faster successor |
| Levenshtein distance only | Too sensitive to length differences; fails on OCR transpositions |
| Phonetic matching (Soundex/Metaphone) | Poor on Devanagari transliterations; English-biased |

---

## 14. Structured Logging

### `structlog`

**Chosen because:**
- Outputs machine-parseable JSON in production; human-readable coloured console in dev.
- Per-stage context binding (`structlog.contextvars.bind_contextvars(document_id=...)`) propagates without passing logger objects everywhere.
- Works natively with Python's `logging` module for third-party library logs.

**Alternatives considered:**

| Option | Why not |
|---|---|
| `loguru` | Good DX but less flexible for structured/machine-readable output |
| Plain `logging` | No structured output; brittle string formatting |
| `pino` (Node) | Only for the Node API layer; Python side needs structlog |

---

## 15. Configuration

### `pydantic-settings`

**Chosen because:**
- Environment variables → Python typed attributes with validation in one step.
- `.env` file support out of the box for local dev.
- Same Pydantic v2 ecosystem as data models — consistent validation behaviour.

---

## 16. Data Validation

### Pydantic v2

**Chosen because:**
- v2 (Rust core) is 5–50× faster than v1 for model validation — important when validating every page's structured JSON output.
- `model_validator`, `field_validator` hooks allow domain-specific rules (e.g., validate `registration_no` format).
- Tight integration with FastAPI for API I/O contracts.

---

## 17. Thresholds Reference

| Parameter | Value | How set | Notes |
|---|---|---|---|
| OCR confidence threshold | **70** | Config (`OCR_CONFIDENCE_THRESHOLD`) | Safety-net gate under the proactive router (§8): page-average confidence below this escalates to the next OCR tier. 70 balances over-flagging (too high) vs accepting garbage (too low). Tunable per document type. |
| Embedding dimensions | **384** | Locked (model choice) | Changing requires full re-embed of all vectors. Do not change without planning a migration. |
| Qdrant distance metric | **Cosine** | Locked (collection init) | Changing requires recreating the collection and re-upserting all vectors. |
| Schema version (manifest) | **1** | `Manifest.schema_version` | Increment when manifest structure changes; enables migration path. |
| Triage handwritten thresholds | **h_cv≥1.10 AND s_cv≥1.80** | Calibrated 2026-06-11 (FIX-035) on real scans | AND logic (replaced weighted blend); one metric over → UNKNOWN → Tesseract + 70-net escalation. `height_weight` removed. Files: `nas/preprocess/triage.py`, `cloud/eval/content_type.py`. |
| Fuzzy match — `FUZZY_MATCH_HIGH` | **90.0** | `cloud/match/models.py` | `>=` → `matched` (dob-fuzzy recovery path). Uncalibrated (no labeled pairs). |
| Fuzzy match — `FUZZY_REVIEW_LOW` | **65.0** (was 75) | Revised 2026-06-12 | `[LOW, HIGH)` → `manual_review`; `<LOW` → `unmatched`. Lowered to recover more dob-fuzzy candidates given reg_no-authoritative policy. Uncalibrated. |
| Match — `NAME_CONFIRM` | **85.0** | `cloud/match/models.py`, added 2026-06-11 | Name score ≥ this on an exact reg_no hit → `matched_on` gains `+name`. Uncalibrated. |
| Match — `NAME_CONFLICT_FLOOR` | **60.0** | `cloud/match/models.py`, added 2026-06-11 | Name present AND score < this on an exact reg_no hit → conflict → dob-fuzzy recovery, else `manual_review`. Uncalibrated. |
| Match — DOB fuzzy tolerance | **±1 day** | Added 2026-06-12 | `timedelta(days=delta) for delta in (-1, 1)` recovery when exact dob differs by one day (common OCR/typo); capped at `manual_review` even on a high name score — never auto-promotes to `matched`. |
| Index — `retrieval_min_results` | **3** | Config (`shared/config.py`), added 2026-06-12 | Retrieval cascade (§20) falls through keyword→graph→vector tiers until this many hits accumulate. |
| Tier-escalation confidence gate | **70** (same as OCR) | Derived | If a tier's page-average confidence < 70, escalate to the next OCR tier (§8). May need independent tuning. |
| Vector search top-k | **TBD** | Query time | How many Qdrant results to return in the vector tier (§20). |

---

## 18. Deferred / Pending Decisions

| Decision | Status | Risk if delayed |
|---|---|---|
| Blank page pixel-variance threshold | Not calibrated | Blank pages will hit OCR unnecessarily, wasting compute |
| Fuzzy match threshold value | Not set | Either too many false substitutions or too many manual_review flags |
| torch / sentence-transformers as optional extras | Accepted for now (~2GB install) | Slow cold starts on Lambda if not containerised |
| Pre-commit hooks (ruff + mypy) | Deferred | Code quality drift in fast-moving dev phase |
| Heavy dep split | Low priority | Revisit before Lambda deployment |
| VLM model tuning (cloud OCR + structure) | Resolved (model) / Pending (calibration) | Done via OpenRouter `google/gemini-2.5-flash` (§8). Cost/accuracy on real sample PDFs not yet benchmarked. Qwen/Gemma local VLM dropped. |
| OpenRouter API key | Pending | VLM tier implemented but unexercised; OpenRouter integration test skipped until `OPENROUTER_API_KEY` set. Now the *only* cloud-OCR credential (GCV removed 2026-06-09). |
| Operations / control dashboard | **Built** | Next.js SPA + FastAPI JSON API (`/api/*`). DASH-1 operational dashboard live. DASH-2 cost tracking implemented via Engine Room v2 (`cloud/engine_room/cost_tracking.py`). DASH-3 eval lab (`/eval`) built for triage calibration. See §15. |

---

## 19. Operations / Control Dashboard

> **Status: BUILT.** Next.js SPA (`web/`) over FastAPI JSON API (`cloud/dashboard/api.py`).
> Auth: signed-cookie sessions + bcrypt (`dashboard_users`). DASH-1 operational
> dashboard live. DASH-2 cost tracking implemented via Engine Room v2.
> DASH-3 eval lab (`/eval`) built for triage calibration. See APP_DOCUMENTATION §15.

A web dashboard to **monitor + control** the pipeline. Originally planned as
FastAPI + HTMX/Jinja; evolved to Next.js SPA for better UX.

### Tech decision — Next.js SPA + FastAPI JSON API

| Option | Decision | Why |
|---|---|---|
| **Next.js SPA + FastAPI JSON API** | **Chosen** | Better UX for document viewer, metrics, and audit. FastAPI `/api/*` endpoints serve JSON; Next.js handles UI. Same auth (signed-cookie). |
| FastAPI + HTMX/Jinja | Rejected | HTMX/Jinja was DASH-1 prototype; Next.js gives better document viewer + real-time SSE. |
| Separate React/Vue SPA | Rejected | Whole new JS toolchain + build step + CORS; more polish than this internal ops tool needs. |
| Streamlit / Gradio | Rejected | Separate process; weak control over layout/flow; awkward to wire to the existing auth + control seams. |

### Decomposition (built)

| Phase | Status | Notes |
|---|---|---|
| **DASH-1 — Operational dashboard** | ✅ Built | Doc list w/ stage status; doc/page detail; trigger ingest; idempotent re-drive; match-rate aggregates; `audit_log`; SSE live status. |
| **DASH-2 — Cost & usage tracking** | ✅ Built | `cost_events` table (schema.sql); Engine Room v2 (`cloud/engine_room/cost_tracking.py`) provides per-stage + per-run cost summary via `GET /api/engine/costs/summary`. |
| **DASH-3 — Accuracy eval lab** | ✅ Built | `/eval` route: enrol pages → label typed/handwritten → score + threshold sweep (`cloud/eval/content_type.py`). Never auto-writes thresholds. |

---

## 20. Retrieval Strategy — Lean Ownership Propagation

> **Decided 2026-06-09 (brainstorm), shipped 2026-06-10**
> (`feat/lean-ownership-retrieval`, merged → main).
> Spec: `docs/superpowers/specs/2026-06-09-lean-ownership-propagation-retrieval-design.md`.
> Plan: `docs/superpowers/plans/2026-06-09-lean-ownership-propagation-retrieval.md`.

### The shift

This system is ultimately a **document-retrieval** system: the admin asks *"the
Aadhaar document of Niraj Chopda (+ optional registration number)"* and expects
the page(s)/PDF back. The original pipeline transcribed **every page** (Tesseract
→ VLM) and ran **per-page LLM entity extraction** on all of them — up to ~26 paid
LLM calls for a 13-page bundle.

We pivoted to **ownership propagation**: a practitioner bundle is **one person's**
application packet. The owner identity (name + permanent `RegistrationNo`) lives
on the **identity pages** (`cover`/`form` → refined to `app_cover`/
`application_form`), 1–2 pages per bundle. Resolve the owner **once** from those
pages, then **propagate** it to every page by bundle context. To make an Aadhaar
page *findable* we do not need its verbatim text — we need (a) what kind of page
it is and (b) whose bundle it belongs to.

Retrieval therefore reduces to a **structured filter**: `owner × page_type` over
Postgres, gated to verified owners (`documents.match_status='matched'`).

### Why we did it

| Driver | Detail |
|---|---|
| **Cost** | VLM (OpenRouter) transcription + structure-LLM are the paid calls. Restricting both to the 1–2 identity pages cuts a 13-page bundle from ~26 paid LLM calls to ~4–6 (**≈75–80% reduction**). Tesseract is local/free, so non-identity pages still get cheap text for typing. |
| **Latency** | Proportional drop on the per-page hot path — fewer network round-trips to the VLM. |
| **It's enough for the query** | "Aadhaar of <person>" is answerable as `owner × page_type` with zero transcription of the Aadhaar page. The owner is the join; the page_type is the filter. |
| **Accuracy** | Reserving the VLM for the identity pages that actually carry the name/reg/dob focuses spend where extraction correctness matters. |

### Design pieces

1. **Per-page routing (OCR).** Identity pages → full Tesseract→VLM ladder + structure-LLM extraction. Non-identity pages → Tesseract-only; a keyword page-typer (`cloud/ocr/page_type.py`) assigns the fine `page_type`, escalating to a cheap VLM **classify** call (label, not transcription) when keyword confidence < 0.5. (§8 revision 2026-06-10.)
2. **Owner resolution + verification (Match).** The owner is resolved from the identity pages and **verified-exact**: an exact `registration_no` hit against the 92K registry is accepted only after a name(+dob) cross-check. This closed a real **FALSE-MATCH** bug — the application form's number can be a *provisional* number that collides with a *different* person's permanent `registration_no` in the registry (the registry is keyed on the permanent number). Identity disagreement → recover the correct person via dob-fuzzy, else `manual_review`. See `error_fixes.md` FIX-033. **Trade-off:** a correct exact hit on a doc that OCR'd no name AND no dob now degrades to `manual_review` (under-extracted docs need a human) — accepted to eliminate silent wrong-person matches.
3. **Propagation gate (Persist + Retrieval).** Only a **verified** owner is trusted: retrieval requires `match_status='matched'`, and Persist preserves a `manual_review` status (never promotes it to `processed`). Qdrant embeds identity-page text only (§5); Neo4j `Page` nodes carry `page_type`.
4. **Retrieval (`cloud/retrieval/service.py`, `GET /retrieve`).** Resolve person by exact `registration_no` or fuzzy name (rapidfuzz over the small matched-doc set), then filter `pages.page_type` under the verified-owner gate; return the page image S3 key + parent PDF S3 key.

### Scope + what we gave up (locked in brainstorm)

| Decision | Choice | Why |
|---|---|---|
| By-person retrieval scope | **Practitioner bundles only** | They are single-owner, so ownership propagation covers 100% of by-person retrieval. Govt letters + record books are multi-owner — out of by-person scope here (a later, heavier per-mention path if needed). |
| Page typing for non-identity pages | **Free Tesseract keywords + VLM-classify escalation** | Reuses the existing T1→T2 confidence-ladder shape; $0 for clean pages, one cheap label call for hard ones. (Calibration of the keyword map + 0.5 net is a TODO via the eval lab.) |
| Datastores | **Postgres backbone + light Qdrant** | The example query is a pure structured filter. Qdrant kept (identity-text only) because "we don't know what the admin will query" — covers unforeseen queries on applicant data (college, qualification, place, year). |
| Deep content *inside* a cert/letter page | **Not extracted** | The explicit cost trade-off: queries that hinge on free-text buried in a non-identity page are not served. Accepted for the cost/latency win. |

### Alternatives considered / rejected

| Option | Why not |
|---|---|
| Transcribe every page + embed all page text (original) | The cost/latency the pivot exists to remove; most of that text is never queried. |
| VLM-classify every page for its type | Robust but pays an API call on every page; the free keyword typer handles clean pages, escalation handles the rest. |
| Visual-only page typing (no OCR) | Truly $0 but brittle across document variety (SSC vs HSC marksheets look alike) and needs training/calibration. |
| Drop Qdrant entirely (pure structured) | Tempting (the example query needs no vectors), but rejected to keep a semantic backup for unanticipated queries on applicant data. |
| Trust the exact `registration_no` match without identity check (original) | The FALSE-MATCH bug — provisional/permanent number-space collisions silently mis-attribute a whole bundle. |

### Addendum 2026-06-12 — Retrieval-first transition (3-tier cascade + index stage)

The `owner × page_type` filter (above) remains correct for its query shape but
assumes the caller already knows the owner's name/reg_no and the desired
`page_type`. To answer more open-ended natural-language queries without falling
back to "embed everything" (the cost problem §20 exists to avoid), a new
**index** stage (`cloud/index/`) runs after persist and adds three cheap,
already-partially-built signals per document/page: a short LLM **summary**
(`document_summary`/`page_summary`), **keywords** (TF-IDF or LLM, mode-selectable
via `index_keyword_mode`, stored in `search_keywords JSONB` + GIN index), and a
6-type **entity** list (`index_entities JSONB` — practitioner/organization/
vendor/government_body/educational_institute/hospital; deliberately a different
column from `pages.structured_json["entities"]` to avoid shadowing the
identity-page entity extraction from §5.7).

`cloud/retrieval/service.py` then runs a **3-tier cascade** for `GET /search`:
keyword tier (Postgres `search_keywords @>` containment, cheapest) → graph tier
(Neo4j traversal over the now-summary/keyword/entity-enriched `Person`/`Entity`/
`Page` nodes) → vector tier (existing Qdrant identity-page embeddings, §5/§7).
Tiers run in order until `retrieval_min_results` (default 3) hits accumulate;
`_merge_hits` dedupes on `document_id`, keeping the highest-tier hit.
`query_parser.py` (LLM-first, keyword-split fallback) turns the NL query into a
`QueryIntent`; `explainer.py` attaches a tier-specific explanation to each
`RetrievalHit`.

**Why a cascade and not "always vector":** the keyword/graph tiers are free
(Postgres/Neo4j, already-written data) and resolve the majority of practical
queries (named entity + document type); vector search is reserved for the
residual unanticipated-query case the original §20 design called out. This
keeps the "Qdrant = light semantic backup" framing intact while giving the
admin a single `GET /search` entry point instead of requiring `owner × page_type`
inputs up front.

**Status:** implemented on `claude/confident-albattani-b184b8` (16 tasks, 45 unit
green, integration + benchmark scaffolds gated), not yet merged to `main`.

## 10. Cloud Infrastructure (AWS Phase 0, 2026-06-16)

- **Principle**: Zero Docker in production. All production services are AWS managed (RDS, S3, SQS, ElastiCache, Lambda, ECS Fargate, CloudWatch, Secrets Manager). Docker only for local dev (optional, can be eliminated).
- **Region**: `ap-south-1` (Mumbai) — lowest latency for India, no data residency concerns.
- **Deployment tool**: SAM CLI for CloudFormation (Phase 0). Terraform branch (`Terraform-prod`) preserved as reference for comparison. SAM chosen for faster iteration, YAML-native, Lambda-native. Terraform may be re-evaluated for production if complexity grows.
- **Compute model**: Lambda for pipeline stages (serverless, pay-per-invocation, auto-scaling, cold starts acceptable for async processing). ECS Fargate for API (always-on, WebSocket-capable, FARGATE_SPOT weighted 3:1 for cost).
- **Storage**: S3 for raw documents, rendered images, manifest.json. RDS PostgreSQL 16 (t3.micro) for structured data + pgvector for embeddings. ElastiCache Redis (cache.t4g.micro) for session cache, rate limiting, job queues.
- **Messaging**: SQS FIFO queues for ordered pipeline processing (ocr → vlm → structure → match → persist). S3 event notifications trigger `ocr-queue.fifo`. Each Lambda stage pushes to next queue. Dead-letter queues (DLQs) for all.
- **Security**: Secrets Manager for all credentials (LLM, VLM, Tesseract, database, Redis), KMS-encrypted, auto-rotation. IAM roles with least-privilege. VPC security groups for RDS/ElastiCache (no public IP). CloudTrail for audit logging.
- **Monitoring**: CloudWatch dashboard with custom metrics (queue depths, processing latency, error rates, cost per document). 4 alarms: queue depth, error rate, API latency, cost threshold. CloudWatch Logs for Lambda/ECS.
- **Cost target**: ~$89/month base + ~$6 per 200-document batch. Breakdown: RDS ~$45, ElastiCache ~$12, ECS ~$15, S3 ~$2, Vercel ~$15. Lambda: ~$0.05 per 200 docs. SQS: ~$0.05 per 200 docs.
- **Config**: `shared/config.py` extended with AWS fields. `database_url` property auto-falls-back from RDS to local (for dev). `aws_clients.py` uses `@lru_cache(maxsize=1)` singleton pattern for boto3 clients.
- **NAS upload agent**: `nas/upload_agent.py` — zero-Docker Python-only. Renders PDFs (PyMuPDF 300 DPI), preprocesses (OpenCV: grayscale, denoise, deskew, adaptive threshold), classifies (Tesseract keyword-based), uploads to S3. `manifest.json` uploaded LAST to trigger S3 event → SQS. Batch mode: asyncio.Semaphore(workers) for concurrent uploads.
- **Lambda stubs**: 6 functions (`cloud/lambda/{ocr,vlm,structure,match,persist,index}/handler.py`) — identical pattern: `lambda_handler(event, context)` → parse SQS records → log → return `{"batchItemFailures": []}`. Phase 1 replaces with actual imports from `cloud/{ocr,structure,match,persist,index}`.
- **Deploy/Destroy**: `cloud/infrastructure/scripts/deploy.py` — one-command interactive deploy. `cloud/infrastructure/scripts/destroy.py` — one-command teardown with confirmation. Both validate prereqs, handle VPC/subnet detection, prompt for external credentials.
- **Makefile**: 15+ AWS targets: `aws-deploy`, `aws-destroy`, `aws-deploy-non-interactive`, `aws-logs-{ocr,vlm,structure,match,persist,index}`, `aws-sqs-status`, `ecr-login`, `build-api`, `push-api`, `upload-aws`, `upload-aws-batch`, `aws-cost-estimate`.
- **Trade-off**: Lambda cold starts add ~1-2s per stage. Acceptable for async batch processing. For real-time (Phase 2), ECS Fargate API is always warm. Consider Lambda Provisioned Concurrency for high-volume stages if cold starts become problematic.
- **Trade-off**: S3 + SQS adds latency vs direct Lambda invocation. Benefit: decoupling, retry, DLQ, ordered processing. S3 event notifications are reliable and free. SQS costs are negligible (~$0.05 per 200 docs).
- **Trade-off**: RDS t3.micro is burstable, may throttle under sustained load. For 200-doc batches (takes ~30 min), it's sufficient. Consider t3.small or t3.medium if concurrent batches are needed.
- **Trade-off**: ElastiCache cache.t4g.micro is tiny. For session cache + rate limiting, it's sufficient. For larger workloads, upgrade to cache.t4g.small.
- **Risk**: SAM template is 47KB and complex. Consider splitting into nested stacks if it grows. CloudFormation has a 500KB template limit. Use `AWS::Serverless::Application` for nested stacks.
- **Risk**: Secrets Manager auto-rotation requires a rotation Lambda. For now, manual rotation is acceptable. Add rotation Lambda in Phase 2.
- **Risk**: ECS Fargate SPOT tasks can be interrupted. Weighted 3:1 means ~25% of tasks are SPOT. For a single-task API, this means ~25% chance of interruption. For development, this is acceptable. For production, use FARGATE only or implement graceful shutdown.
- **Risk**: Lambda stubs are non-functional. Phase 1 must replace them with actual pipeline imports. This is the highest risk item for Phase 1.
- **Next**: Phase 1 (TDD) begins. All implementation must be test-driven. First tests: S3→SQS→Lambda chain integration, Lambda stub replacement, API Docker image build, Vercel deploy.
