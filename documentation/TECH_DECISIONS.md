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
| **T2** | Google Cloud Vision `DOCUMENT_TEXT_DETECTION` | Handwriting (English + Devanagari) | ✅ done |
| **T3** | Gemini VLM via OpenRouter (`google/gemini-2.5-flash`) | Messy / Vision-flunk edge cases | ✅ done |

Escalation is by **difficulty (typed → handwritten → messy)**, not by language —
one tool (GCV) covers handwritten-English *and* handwritten-Devanagari, so we
don't fan out per script.

### T1 — Tesseract (via `pytesseract`)

- `image_to_data(output_type=DICT)` returns per-word confidence + bounding
  boxes — feeds the confidence-net gate.
- `eng+mar+hin` language packs; handles Devanagari reasonably on *typed* text.
- Open source, no API cost, runs locally on NAS / in Lambda.

### T2 — Google Cloud Vision (`DOCUMENT_TEXT_DETECTION`)

- **Vendor = Cloud Vision, not Document AI** — Vision's dense-text mode covers
  handwritten English and handwritten Devanagari in one call.
- Auth via `GOOGLE_APPLICATION_CREDENTIALS` → `Settings.google_application_credentials`;
  absent creds degrade gracefully to `TierNotImplemented`.
- Sync SDK (`google-cloud-vision>=3.7`) wrapped in `anyio.to_thread.run_sync`
  (mirrors the TesseractTier pattern); word-level parsing, conf ×100.

### T3 — Gemini VLM (via OpenRouter)

- Last-resort tier for messy scans / pages the lower tiers flunk. VLM reads the
  page image directly (no character segmentation).
- **Transport = OpenRouter**, reached with the `openai` SDK pointed at
  `OPENROUTER_BASE_URL` (OpenAI-compatible Chat Completions). The user runs on
  OpenRouter, so we go through it rather than Google AI Studio direct or Vertex
  AI. Model id `google/gemini-2.5-flash` (OpenRouter-namespaced).
- Auth via `OPENROUTER_API_KEY` → `Settings.openrouter_api_key`; absent →
  `TierNotImplemented` (graceful degradation). Image sent as a base64
  `image_url` data-URL. Sync call offloaded via `anyio.to_thread.run_sync`.

**Alternatives considered / rejected:**

| Option | Why not |
|---|---|
| **AWS Textract** | **Rejected** — no Devanagari (only eng/spa/ger/fre/ita/por; handwriting English-only). |
| **Qwen / Gemma local VLM** | **Superseded** — was the old reactive fallback; replaced by the GCV (T2) + Gemini (T3) tiers. |
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
| Blank page skip threshold | **TBD** | Config (`BLANK_PAGE_VARIANCE_THRESHOLD`) | Pixel variance below this → skip OCR. Value not yet determined; needs calibration on sample scans. |
| Fuzzy match threshold | **TBD** | Config (`FUZZY_MATCH_THRESHOLD`) | `rapidfuzz` score above this → accept substitution. Needs calibration. |
| Tier-escalation confidence gate | **70** (same as OCR) | Derived | If a tier's page-average confidence < 70, escalate to the next OCR tier (§8). May need independent tuning. |
| Vector search top-k | **TBD** | Query time | How many Qdrant results to return before Neo4j re-ranking. |

---

## 18. Deferred / Pending Decisions

| Decision | Status | Risk if delayed |
|---|---|---|
| Blank page pixel-variance threshold | Not calibrated | Blank pages will hit OCR unnecessarily, wasting compute |
| Fuzzy match threshold value | Not set | Either too many false substitutions or too many manual_review flags |
| torch / sentence-transformers as optional extras | Accepted for now (~2GB install) | Slow cold starts on Lambda if not containerised |
| Pre-commit hooks (ruff + mypy) | Deferred | Code quality drift in fast-moving dev phase |
| Heavy dep split | Low priority | Revisit before Lambda deployment |
| Gemini VLM model tuning (T3 OCR + structure) | Resolved (model) / Pending (calibration) | T3 done via OpenRouter `google/gemini-2.5-flash` (§8). Cost/accuracy on real sample PDFs not yet benchmarked. Qwen/Gemma local VLM dropped. |
| OpenRouter API key | Pending | T3 implemented but unexercised; OpenRouter integration test skipped until `OPENROUTER_API_KEY` set. |
| Google Cloud Vision credentials / project | Pending | T2 implemented but unexercised; GCV integration test skipped until `GOOGLE_APPLICATION_CREDENTIALS` set. |
