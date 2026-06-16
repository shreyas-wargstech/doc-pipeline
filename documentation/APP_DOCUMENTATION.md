# Document Intelligence Pipeline — Full Application Documentation

> **Version:** 2.3 · **Last updated:** 2026-06-16 · **Status:** Pipeline complete end-to-end (ingest→classify→OCR→structure→match→persist→index→retrieve); validated on 3 real practitioner bundles, all `matched`. Phase 2 Intelligence layer complete (7 features: Human Corrections Learning Loop, AI Narratives, AI Context Sidebar, Predictive Self-Healing Pipeline, Identity Intelligence v1, Dynamic Cost Router v1, Engine Room v2). All major merges complete on local `main`. Cost optimization: FIX-048 (image resize for page-type classify, 4–10× token reduction) deployed, measurement pending.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Layout](#2-repository-layout)
3. [Architecture Overview](#3-architecture-overview)
4. [Infrastructure & Local Dev](#4-infrastructure--local-dev)
5. [Pipeline Stages](#5-pipeline-stages)
   - 5.1 Ingest
   - 5.2 Split
   - 5.3 Preprocess
   - 5.4 Classify
   - 5.5 OCR (proactive tier routing + identity-scoped transcription)
   - 5.6 Confidence Handling
   - 5.7 Structure
   - 5.8 Match
   - 5.9 Persist
6. [Data Contracts](#6-data-contracts)
   - 6.1 Manifest
   - 6.2 Postgres Schema
   - 6.3 Qdrant Collection
   - 6.4 Neo4j Graph Schema
7. [NAS Side (Upload Agent)](#7-nas-side-upload-agent)
8. [Cloud Side (Processing Pipeline)](#8-cloud-side-processing-pipeline)
9. [Shared Libraries](#9-shared-libraries)
10. [Initialisation Scripts](#10-initialisation-scripts)
11. [Configuration & Environment](#11-configuration--environment)
12. [Testing Strategy](#12-testing-strategy)
13. [Makefile Targets](#13-makefile-targets)
14. [Retrieval Design (lean ownership propagation)](#14-retrieval-design)
15. [Operations Dashboard (Next.js + FastAPI JSON API)](#15-operations-dashboard)
16. [Phase 2 Intelligence Layer](#16-phase-2-intelligence-layer)
    - 16.1 Human Corrections Learning Loop
    - 16.2 AI-Generated Document Narratives
    - 16.3 AI Context Sidebar
    - 16.4 Predictive Self-Healing Pipeline
    - 16.5 Identity Intelligence
    - 16.6 Dynamic Cost Router
    - 16.7 Engine Room v2
17. [Production Migration Path](#17-production-migration-path)
18. [Open Items & Known Gaps](#18-open-items--known-gaps)

---

## 1. Project Overview

The **Document Intelligence Pipeline** ingests scanned multi-page PDFs (practitioner registration bundles from a healthcare council), extracts structured data via OCR + LLM augmentation, and stores results in a vector database (Qdrant) and a graph database (Neo4j) for semantic + structured retrieval.

### Primary Use Case
A council officer can query:
> *"Documents of Ashish, DOB 26 Feb 1996"*

The system resolves this to a ranked, highlighted set of matching scanned PDFs without manual search.

### Document Profile
- PDFs are **multi-document bundles**: application form, government receipts, Aadhaar, SSC/HSC marksheets, degree certificates, internship certificates, provisional registration certificate, Form E, marriage certificate (where applicable), blank back-of-page scans.
- Languages: **English + Marathi + Hindi (Devanagari script)** mixed on the same page.
- Volume: ~92,389 rows of ground-truth practitioner reference data in Excel (36 columns).
- Natural key: `RegistrationNo` (printed on every page; sometimes QR-encoded).

---

## 2. Repository Layout

```
root/
├── shared/                         # Code used by both NAS + Cloud
│   ├── config.py                   # pydantic-settings: all env vars
│   ├── hashing.py                  # Streaming SHA-256 (document_id)
│   ├── storage_s3.py               # Async S3/MinIO client, put_if_absent, get_s3_client()
│   ├── logging.py                  # structlog JSON/console setup
│   ├── exceptions.py               # Stage-specific exception hierarchy (PipelineError tree)
│   ├── db.py                       # Async SQLAlchemy engine + session_scope + dispose_engine
│   ├── qdrant_client.py            # get_qdrant(), ensure_collection()
│   └── neo4j_client.py             # get_driver(), session_scope(), ensure_constraints()
│
├── nas/                            # Runs on the local NAS box
│   ├── preprocess/                 # Image preprocessing (OpenCV) + triage.py
│   │   ├── pipeline.py             # 7-step preprocess pass (toggleable)
│   │   └── triage.py               # compute_features / classify_features (content_type), OSD, blank detect
│   ├── manifest/
│   │   └── models.py               # Manifest + PageManifest pydantic v2 models + Literal aliases
│   └── uploader/                   # render.py (PyMuPDF→PNG) + service.py (S3 upload + trigger)
│
├── cloud/                          # Runs on AWS (Lambda container images, serverless)
│   ├── app.py                      # FastAPI: /health, /pipeline/notify, /retrieve, /api/* (dashboard)
│   ├── ingest/
│   │   ├── service.py              # handle_manifest() entry point
│   │   ├── storage_db.py           # DocumentRepository + PageRepository
│   │   ├── models.py               # OcrPageMessage
│   │   └── sqs.py                  # enqueue_page() (aioboto3, FIFO-aware)
│   ├── classifier/                 # rules.py (keyword/regex) + llm.py (OpenRouter fallback) + service.py
│   ├── ocr/                        # router.py (proactive tier routing) + tiers/{tesseract,vlm}.py
│   │   ├── page_type.py            # keyword page-typer + VLM-classify escalation (lean retrieval)
│   │   └── consumer.py             # SQS/Lambda record handler → process_page
│   ├── structure/                  # regex_extract.py + llm.py + service.py (identity-page entity extraction)
│   ├── match/                      # fuzzy.py + reference.py + service.py (reg_no-authoritative match)
│   ├── persist/                    # summary.py + embeddings.py + qdrant_writer.py + graph.py + service.py
│   ├── index/                      # models.py + summarizer.py + keywords.py + entities.py + db_writer.py + neo4j_writer.py + handler.py + consumer.py
│   ├── retrieval/                  # query_parser.py + explainer.py + service.py — 3-tier cascade (keyword/graph/vector)
│   ├── eval/                       # content_type.py — pure threshold-sweep scoring (DASH-3)
│   ├── dashboard/                  # api.py (JSON /api/*) + session.py (signed-cookie auth) + sse.py
│   │                               #   + queries.py + actions.py + audit.py + eval_queries.py
│   ├── corrections/              # Phase 2: human corrections service (store/get/analyze) + nightly learning loop
│   ├── narratives/                 # Phase 2: AI-generated document narratives (template-based summaries)
│   ├── context/                    # Phase 2: AI context sidebar (cross-reference DB queries)
│   ├── self_healing/               # Phase 2: predictive self-healing (name variations, hidden identity pages, stuck monitor, retry logic)
│   ├── identity/                   # Phase 2: identity intelligence v1 (cross-page consistency checks)
│   ├── ocr/                        # router.py (proactive tier routing) + tiers/{tesseract,vlm}.py + cost_router.py (Phase 2: failure prediction)
│   └── engine_room/                # Phase 2: Engine Room v2 (tuner.py, ab_test.py, cost_tracking.py) + diagnostics/health/inspector
│
├── web/                            # Next.js dashboard SPA (replaces HTMX) — documents/detail/metrics/audit/eval
│
├── scripts/
│   ├── init_{postgres,minio,qdrant,neo4j,sqs,all}.py
│   ├── load_reference_data.py      # Excel → reference_data bulk load (92,389 rows loaded)
│   ├── apply_migration_001.py      # app_no INTEGER → BIGINT
│   ├── apply_eval_table.py         # idempotent eval_content_type table apply
│   ├── apply_corrections.py        # nightly: analyze human_corrections → update keyword rules, substitution maps, thresholds
│   ├── upload_pdf.py               # NAS uploader CLI
│   ├── run_ocr_worker.py           # drains elasticmq → process_page
│   ├── run_structure.py / run_match.py / run_persist.py   # per-document stage runners
│   └── add_dashboard_user.py       # seed a dashboard login (bcrypt)
│
├── tests/                          # shared/ nas/ cloud/ — integration gated behind -m integration
│
├── docs/
│   ├── INTEGRATION.md              # Service deep-dive + troubleshooting
│   └── superpowers/{specs,plans}/  # per-stage design specs + execution plans
│
├── documentation/                  # ← You are here
│   ├── APP_DOCUMENTATION.md
│   ├── TECH_DECISIONS.md
│   ├── session_log.md              # per-session durable detail (ground truth after code/tests)
│   └── error_fixes.md              # FIX-001..033 — symptom/root-cause/fix/rule
│
├── db/
│   ├── schema.sql                  # Postgres DDL (authoritative)
│   └── migrations/                 # 001_app_no_bigint.sql
├── docker-compose.yml              # postgres, minio, qdrant, neo4j, elasticmq, api, web
├── elasticmq.conf                  # local SQS (FIFO queue)
├── pyproject.toml
├── Makefile
├── .env.example
└── README.md
```

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          NAS BOX (local)                        │
│                                                                 │
│  PDF arrives → sha256 hash → split pages → preprocess images   │
│       → build manifest.json → upload all to S3                 │
│       → HTTP POST /pipeline/notify  (dev shim)                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │ S3 event (prod: SQS → Lambda)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       CLOUD PIPELINE                            │
│                                                                 │
│  handle_manifest()                                              │
│      │                                                          │
│      ├─► Classify bundle (practitioner | letter | …)           │
│      │     rules-first keyword/regex → OpenRouter LLM fallback │
│      │                                                          │
│      ├─► For each page (proactive tier routing):               │
│      │       identity page (cover/form): Tesseract→VLM ladder  │
│      │       every other page: Tesseract-only (keyword typer)  │
│      │         └─► VLM-classify (label only) if kw conf < .5   │
│      │                                                          │
│      ├─► Structure (identity pages only):                       │
│      │       regex pre-pass + OpenRouter LLM → entities,       │
│      │       page_type, practitioner identity rollup           │
│      │                                                          │
│      ├─► Match practitioner docs vs reference_data (92K rows)   │
│      │       VERIFIED-EXACT: reg_no hit + name(+dob) check;    │
│      │       conflict → dob-fuzzy recover → else manual_review │
│      │                                                          │
│      └─► Persist: Postgres status + Qdrant (identity pages)    │
│                   + Neo4j (MERGE)                              │
│                                                                 │
└───────────────────────────────────────┬─────────────────────────┘
                                        │
          ┌─────────────────────────────┼────────────────────────┐
          ▼                             ▼                        ▼
       Postgres                      Qdrant                   Neo4j
   (metadata + match            (384-dim semantic          (graph: Document
    status + JSONB —             embeddings — IDENTITY      → Page → Person
    retrieval backbone)          PAGES ONLY, light backup)  → Entity → ReferenceRecord)
```

> **Retrieval is structured, not semantic-first (revised 2026-06-10).** A practitioner
> bundle is one person's packet: resolve the owner once from the identity pages, propagate
> by bundle context, then retrieve `owner × page_type` over Postgres (gated to verified
> owners). Qdrant is a light semantic backup over identity-page text only. See §14.

### Trigger Flow (dev vs prod)

| Environment | Trigger |
|---|---|
| **Dev** | `HTTP POST /pipeline/notify` from NAS uploader after manifest upload (uploader CLI `--trigger direct|http`). Local SQS = real **elasticmq**; OCR worker drains it via `scripts/run_ocr_worker.py`. |
| **Prod** | S3 `s3:ObjectCreated` on `manifest.json` → SQS → Lambda → `handle_manifest()` (auto-trigger chaining structure→match→persist still TODO — see §18). |

---

## 4. Infrastructure & Local Dev

### Services (docker-compose)

| Service | Image | Port | Purpose |
|---|---|---|---|
| Postgres | `postgres:16` | 5432 | Metadata, match state, reference data |
| MinIO | `minio/minio` | 9000 / 9001 | S3-compatible local blob storage |
| Qdrant | `qdrant/qdrant` | 6333 | Vector similarity search |
| Neo4j | `neo4j:5` (APOC) | 7474 / 7687 | Graph traversal + entity relationships |

### Quick Start

```bash
make up          # Start all 4 containers
make install     # uv sync --extra dev
make init        # Run all init scripts (idempotent)
make test        # Unit tests (no containers needed)
make test-integration  # Integration tests (containers must be up)
```

### Environment Variables (`.env.example`)

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/docpipeline
S3_ENDPOINT_URL=http://localhost:9000
S3_BUCKET=documents
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=document_pages
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# SQS (local = elasticmq). Keep blank vars truly blank — NO inline comments (FIX-027).
SQS_OCR_QUEUE_URL=http://localhost:9324/000000000000/ocr-pages.fifo
AWS_REGION=us-east-1
SQS_ENDPOINT_URL=http://localhost:9324

# Cloud OCR / LLM — OpenRouter is the SOLE cloud credential (GCV removed 2026-06-09)
OPENROUTER_API_KEY=                 # absent → VLM/LLM stages degrade gracefully
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=google/gemini-2.5-flash

# Dashboard
SESSION_SECRET=                     # HMAC signing key for signed-cookie auth
```

> Local run also needs **tesseract on PATH** with `eng+mar+hin`+`osd` traineddata (language
> packs live at the tessdata repo ROOT, not `/script` — FIX-027).

---

## 5. Pipeline Stages

### 5.1 Ingest

**Responsibility:** Accept a manifest, validate it, record document + page metadata in Postgres, verify S3 assets exist.

**Entry point:** `cloud/ingest/service.py → handle_manifest(manifest: Manifest)`

**Key operations:**
- Validate `manifest.json` via `Manifest` pydantic model.
- Idempotent upsert of `documents` row via `DocumentRepository`.
- Idempotent upsert of one `pages` row per page via `PageRepository`.
- Both upserts use `ON CONFLICT DO UPDATE` (SQLAlchemy 2.0 async + asyncpg).

**Idempotency key:**
- `documents`: `document_id` (SHA-256 of original PDF)
- `pages`: `(document_id, page_num)`

**Error types:** `IngestError`, `ManifestError` (from `shared/exceptions.py`)

---

### 5.2 Split

**Responsibility (NAS side):** Split the incoming PDF into per-page PNG images.

**Tools:** PyMuPDF (`fitz`) for page extraction; `pdf2image` as fallback for rasterization.

**Output:** `documents/<doc_id>/pages/page_NNN.png` uploaded to S3.

**Blank page detection:** Pages below a pixel-variance threshold are flagged as `page_type = blank` in the manifest and skipped for OCR.

---

### 5.3 Preprocess

**Responsibility (NAS side):** Improve image quality before OCR.

**Steps (all toggleable):**
1. Convert to greyscale
2. Denoise (OpenCV `fastNlMeansDenoising`)
3. Deskew via Hough transform or projection profile
4. Rotation correction (0°/90°/180°/270° detection)
5. Adaptive thresholding (Otsu or Sauvola)

**Debug mode:** Each intermediate step saved as a separate artifact.

**Config flags:** `PREPROCESS_DENOISE`, `PREPROCESS_DESKEW`, `PREPROCESS_THRESHOLD` (all bool, default `true`)

---

### 5.4 Classify

**Responsibility:** Determine `document_category` (practitioner | letter | receipt | record | other) + sub-type, and set routing flags.

**Entry point:** `cloud/classifier/service.py → classify(manifest, *, trust_manifest_hint=True)`

**3-path logic:**
1. **Manifest hint** — if the NAS set a category and `trust_manifest_hint` (confidence 0.85). (Dashboard re-classify passes `False` to force the cover-text path.)
2. **Rules engine** (`rules.py`) — weighted keyword/regex over cover text (PyMuPDF text layer first, Tesseract OCR of page 1 as fallback). Below `MIN_SCORE_THRESHOLD` → LLM.
3. **LLM fallback** (`llm.py`, OpenRouter, same creds as the VLM tier) — JSON category + sub-type; parse failure → graceful `("other", None, 0.4)`; absent key → `ClassifierError`.

**Routing:** all real categories → full OCR pipeline; `other` → skip OCR, flag `manual_review` immediately.

---

### 5.5 OCR — Proactive Tier Routing + Identity-Scoped Transcription

**Responsibility:** Get each page *findable*. Under the lean-retrieval design (§14) that means: full text only where the owner identity lives; a page-type label everywhere else.

**Routing model** (`cloud/ocr/router.py`): triage labels each page `content_type` (typed|handwritten|unknown). The router picks a **starting tier** by difficulty and escalates on failure / low confidence.

| Tier | Engine | Handles |
|---|---|---|
| **T1** | Tesseract `eng+mar+hin` (`pytesseract.image_to_data`) | typed/printed pages; per-word conf + bbox feed the 70-net |
| **T2** | VLM via OpenRouter (`google/gemini-2.5-flash`, tier name `vlm`) | handwriting (English + Devanagari) + messy scans + low-conf escalation |

> GCV (old T2) removed 2026-06-09 — ladder collapsed to `(tesseract, vlm)`; OpenRouter is the sole cloud OCR credential. Old reactive Qwen/Gemma cascade abandoned (Tesseract emits *confident garbage* that slips the gate).

**Identity-scoped transcription (lean retrieval, 2026-06-10):**
- **Identity pages** (coarse `page_type` `cover`/`form`) get the full Tesseract→VLM ladder (real transcription).
- **Every other page** is **Tesseract-only** (no paid VLM transcription). Its fine `page_type` is assigned by a cheap keyword typer (`cloud/ocr/page_type.py`), escalating to a VLM **classify** call (a single label, NOT a transcription) only when keyword confidence < 0.5.
- **Cost optimization (FIX-047/047b/048, 2026-06-15):** blank-page short-circuit + keyword rules for uncovered types (`invoice`/`letter_body`) + image resize (768px) before VLM classify reduces classify cost ~75% ($0.069→$0.007–0.017 estimated on a 13-page bundle).
- Cuts a 13-page bundle from ~26 paid LLM calls to ~4–6.

**VLM tier notes** (`cloud/ocr/tiers/vlm.py`): no per-word confidence — words get a fixed `_CONF_PRIOR = 85.0` (above the 70 net) + `bbox=(0,0,0,0)`. An unavailable VLM on a handwritten page fails cleanly → `manual_review` (NO fall-back to Tesseract, by design). Unavailable START tier **escalates** (`continue`, not `break` — FIX-028).

**VLM classify image optimization (FIX-048, 2026-06-15):** The classify-only path (for non-identity pages) resizes PNGs to 768px wide before base64-encoding — page-type classification doesn't need full-resolution pixels. OpenCV resize (INTER_AREA, aspect-preserving) reduces image tokens 4–10×. Fallback pass-through if narrower or decode fails.



**Status race guard (FIX-029):** ingest's bulk `QUEUED` write runs *after* SQS enqueue, so it is a guarded transition (`only_from=[PENDING]`) — never downgrades a page a fast worker already marked `done`.

---

### 5.6 Confidence Handling

**Threshold:** 70 (default; configurable via `OCR_CONFIDENCE_THRESHOLD`)

Retained as a **safety net** under the proactive router: a tier's page-average confidence below 70 escalates to the next OCR tier (catches typed pages Tesseract mangles). Token-level fuzzy substitution against `reference_data` is handled downstream by the Match stage (§5.8), not in OCR.

---

### 5.7 Structure

**Responsibility:** Convert OCR `raw_text` into structured entities, refine
`page_type`, and roll up the document-level practitioner identity.

> **Lean retrieval (2026-06-10):** entity extraction runs on **identity pages
> only** (`cover`/`form`/`app_cover`/`application_form`) — the pages that carry
> name/reg/dob. A practitioner doc that resolves no identity → `manual_review`.

**Method (hybrid):**
1. **Regex pre-pass** (`cloud/structure/regex_extract.py`) — deterministic,
   high-precision: `application_number` (AMR-MCH pattern), `registration_no`
   (context-anchored), dates (DD/MM/YYYY, ISO, Devanagari numerals → ISO,
   `1900` sentinels + calendar-invalid dates dropped), phone, email, pincode.
2. **LLM pass** (`cloud/structure/llm.py`, OpenRouter) — refined `page_type`
   (aadhaar/ssc/hsc/marks_statement/…), NER (names, addresses, orgs), and
   identity hints. Regex hits win on exact ID/date collisions.
3. **Rollup** (practitioner only) — best `registration_no` / `applicant_name_raw`
   / `application_number` / `dob` / `gender` across pages → `documents` table
   via `update_fields`. `dob` stored as a DATE.

**Per-page output (stored in `pages.structured_json["entities"]`):**
```json
[
  { "type": "person_name", "value": "Ashish Patil", "confidence": 0.92, "source": "llm" },
  { "type": "registration_no", "value": "34903", "confidence": 0.9, "source": "regex" }
]
```

Entities carry **no bbox** — extraction works off `raw_text`. Token bboxes
remain available in `structured_json["words"]` (T1/T2) if a future highlight
feature needs them.

**Trigger:** `make structure DOC=<id>` (per-document; rollup needs every page
OCR'd). Runs inside `session_scope()`, idempotent, all-or-nothing atomic (transient
LLM error mid-doc rolls back → recover by re-run). Auto-trigger deferred to AWS wiring.

---

### 5.8 Match

**Responsibility:** Resolve + **verify** the practitioner owner against the ~92K-row `reference_data` registry; own the `match_status` column.

**Entry point:** `cloud/match/service.py → match_document` (`make match DOC=<id>`).

**Decision ladder:**
- Non-practitioner → `not_applicable`.
- Practitioner → exact `registration_no` hit, then **VERIFIED-EXACT** (FIX-033): accept the number only after a name (+dob) cross-check. The form's number can be a *provisional* number colliding with a different holder's *permanent* `registration_no`.
- Identity conflict → recover via **dob-gated fuzzy** (rapidfuzz `token_sort_ratio`, max over name fields): ≥`FUZZY_MATCH_HIGH`(90) → `matched`; [75,90) → `manual_review`; <75 → `unmatched`. No dob → `unmatched` (no full 92K scan).

Writes `match_status` + `reference_data_id` + `metadata.match` provenance (`matched_on` includes `registration_no+name`). Does NOT touch `document.status`. Idempotent.

> **Trade-off:** a *correct* exact reg_no hit on a doc that OCR'd no name AND no dob now degrades to `manual_review` — the deliberate cost of eliminating silent wrong-person matches. Fuzzy thresholds UNCALIBRATED (no labeled pairs yet).

---

### 5.9 Persist

**Entry point:** `cloud/persist/service.py → persist_document` (`make persist DOC=<id>`). Idempotent on `document_id`.

**Qdrant** (`qdrant_writer.py`):
- Collection: `document_pages` | Vector: 384-dim Cosine | Model: `paraphrase-multilingual-MiniLM-L12-v2`.
- One vector per **identity page only** (text-bearing: `ocr_status=done` AND non-empty `structured_json["raw_text"]`) — not every page (§14). Point id = `uuid5(NAMESPACE_URL, page_id)` → re-run upserts the same point.
- Vector text = deterministic per-page summary (`summary.py`): `page_type` + grouped/deduped entities + first 512 chars raw_text (front-loaded for the embedder's ~256-tok truncation; NO LLM).

**Neo4j** (`graph.py`) — all writes via `MERGE` (idempotent):
- `Document-[:HAS_PAGE]->Page-[:MENTIONS]->mention`; `Person` (on `registration_no`) `-[:BELONGS_TO]->Document`; matched → `ReferenceRecord` via `[:MATCHES]`. `Page` carries `page_type`.
- Constraints: `Document.document_id` UNIQUE, `Page.page_id` UNIQUE, `(Person.registration_no)` UNIQUE; index on `(Entity.type, Entity.value)`.

**Postgres:**
- Promote `documents.status='processed'` (NEVER downgrades `failed`; **preserves** `manual_review` — propagation gate). Match stage already owns `match_status` + `reference_data_id`.

**Txn model:** Postgres read+status in the caller's `session_scope`; Qdrant + Neo4j can't share it — each independently idempotent, the status flip is the completion signal.

**S3:**
- Original PDF archived at `documents/<doc_id>/original.pdf`.
- Page images at `documents/<doc_id>/pages/page_NNN.png`.

---

## 6. Data Contracts

### 6.1 Manifest (`nas/manifest/models.py`)

```python
# Literal aliases (single source of truth — OcrPageMessage imports these; shared/page_type.py re-exports the typer)
PageType     = Literal["blank", "form", "other"]
ContentType  = Literal["typed", "handwritten", "unknown"]      # triage
LanguageHint = Literal["latin", "devanagari", "mixed", "unknown"]  # triage OSD

class PageManifest(BaseModel):
    page_num: int                          # 1-indexed
    s3_key: str                            # documents/<doc_id>/pages/page_NNN.png
    page_type: PageType = "other"          # NAS-side classify_page_type() result
    content_type: ContentType = "unknown"  # typed vs handwritten → OCR tier routing
    language_hint: LanguageHint = "unknown"  # dominant script (triage OSD)

class Manifest(BaseModel):
    schema_version: int = 1
    document_id: str        # SHA-256 of original PDF
    original_s3_key: str
    document_category: str  # practitioner | letter | receipt | record | other (NAS hint, classifier refines)
    pages: list[PageManifest]
```

> `content_type` + `language_hint` are produced by NAS-side triage (§9 / triage.py)
> and drive the proactive OCR tier router (`typed`→T1 Tesseract, `handwritten`→T2
> Vision). `width`/`height`/`sha256` were dropped from the slim contract.
>
> **NAS-side page typing (FIX-041, 2026-06-12):** `nas/uploader/service.py` runs a
> throwaway `pytesseract.image_to_string` pass on non-blank pages and calls the
> shared `classify_page_type()` (now in `shared/page_type.py`, re-exported by
> `cloud/ocr/page_type.py` for `VlmPageTyper`/router). Any page classified
> `application_form` (any confidence) → manifest `page_type="form"`. This makes
> `form` real at upload time, so the cloud VLM-first identity-page routing
> (§5.5/§5.7/§5.9) fires on first-pass OCR. `cover`/`receipt`/`certificate` were
> dropped from `PageType` — `cover` was folded into `form` (app_cover retirement,
> 2026-06-12); identity-page sets across `cloud/ocr/router.py`,
> `cloud/structure/service.py`, `cloud/persist/service.py` are now simply `{form}`.
> Historical S3 manifests with `page_type="cover"` are unaffected (out of scope).

### 6.2 Postgres Schema (`db/schema.sql`)

**`documents`**

> Status/category columns are `TEXT` + `CHECK` (not Postgres `ENUM` types) — see `db/schema.sql`.

| Column | Type | Notes |
|---|---|---|
| `document_id` | `TEXT PK` | SHA-256 |
| `document_category` | `TEXT CHECK` | practitioner\|letter\|receipt\|record\|other |
| `application_number` | `TEXT` | nullable |
| `registration_no` | `TEXT` | nullable; join key to reference_data |
| `applicant_name_raw` | `TEXT` | nullable; as OCR'd, pre-normalization |
| `dob` | `DATE` | nullable |
| `gender` | `TEXT` | nullable |
| `match_status` | `TEXT CHECK` | NULL (not-yet-matched) \| matched \| unmatched \| not_applicable \| manual_review — match stage owns this column |
| `reference_data_id` | `INTEGER FK` | nullable; → reference_data(id) |
| `metadata` | `JSONB` | category-specific fields; `metadata.match.ocr_extracted` preserves pre-back-fill OCR values |
| `document_summary` | `TEXT` | nullable; index stage (`cloud/index/summarizer.py`) |
| `search_keywords` | `JSONB` | nullable; TF-IDF / keyword-mode terms, GIN indexed — keyword-tier retrieval |
| `index_entities` | `JSONB` | nullable; 6-type LLM entity list (practitioner/organization/vendor/government_body/educational_institute/hospital) — distinct from `pages.structured_json["entities"]` |
| `index_status` | `TEXT CHECK` | pending \| done \| failed — index stage status |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | auto-managed |

**`pages`**

| Column | Type | Notes |
|---|---|---|
| `page_id` | `TEXT PK` | `<document_id>:<page_num>` |
| `document_id` | `TEXT FK` | → documents |
| `page_num` | `INT` | |
| `s3_key` | `TEXT` | PNG location |
| `page_type` | `TEXT` | classifier label (e.g. form, application_form, aadhaar, blank — see `page_types` catalogue) |
| `language_detected` | `TEXT` | eng \| mar \| hin \| mixed |
| `ocr_status` | `TEXT CHECK` | pending \| queued \| done \| failed \| skipped |
| `structured_json` | `JSONB` | LLM/OCR structured output |
| `page_summary` | `TEXT` | nullable; index stage per-page summary |
| `index_status` | `TEXT CHECK` | pending \| done \| failed — index stage status |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |

**`page_types`** — reference catalogue (17 seed rows, no FK on `pages.page_type` — kept free TEXT). Added 2026-06-11.

**`reference_data`**

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGSERIAL PK` | |
| `registration_no` | `TEXT UNIQUE` | natural key |
| *(36 Excel columns)* | various | mirrored from Excel |
| `fields_norm` | `JSONB` | normalised field values; GIN indexed |

### 6.3 Qdrant Collection

```
Collection: document_pages
Vector size: 384
Distance: Cosine
Model: paraphrase-multilingual-MiniLM-L12-v2
Embeds: IDENTITY PAGES ONLY (app_cover/application_form) — light semantic
        backup; primary retrieval is structured owner × page_type (§14).

Payload fields:
  document_id    (keyword)
  page_num       (integer)
  page_type      (keyword)
  entity_types   (keyword[])
  registration_no (keyword, nullable)
  raw_text_snippet (text)
```

### 6.4 Neo4j Graph Schema

```
Nodes
  (:Document   {document_id, category, match_status})
  (:Page       {page_id, page_num, page_type, language_detected})
  (:Person     {registration_no, name_variants[], dob, gender})
  (:Entity     {type, value, source})
  (:Organization {name, org_type})        ← TBD (persist stage)
  (:Vendor       {name})                  ← TBD (persist stage)

Relationships
  (:Document)-[:HAS_PAGE]->(:Page)
  (:Page)-[:MENTIONS]->(:Entity)          ← persist MERGEs mention nodes off structured_json entities
  (:Person)-[:BELONGS_TO]->(:Document)    ← Person merges on registration_no
  (:Person)-[:MATCHES]->(:ReferenceRecord) ← only when match_status='matched'; ref data lives in Postgres
```

---

## 7. NAS Side (Upload Agent)

**Runs on:** Local NAS box (Windows or Linux).

**Responsibilities:**
1. Watch drop folder for new PDFs.
2. Compute SHA-256 → `document_id`.
3. Split PDF into page PNGs (`PyMuPDF`).
4. Preprocess each page image (OpenCV pipeline).
5. Upload `original.pdf` + page PNGs + `manifest.json` to S3.
6. `manifest.json` is **always uploaded last** (it is the trigger artifact).
7. POST to `http://localhost:<port>/pipeline/notify` (dev shim).

**QR Pre-check:** `pyzbar` decodes QR sticker on cover page. If decoded value matches PDF filename pattern → use as `document_id` confirmation. Else fall back to SHA-256 of file.

---

## 8. Cloud Side (Processing Pipeline)

**Entry point:** `cloud/ingest/service.py → handle_manifest()`

**Routing logic:**
```
manifest received
  └─► ingest: validate + record in Postgres
  └─► classify: determine document_category
      ├─► practitioner bundle
      │     └─► match against reference_data (registration_no lookup → fuzzy fallback)
      │     └─► OCR + structure each non-blank page
      │     └─► persist (Qdrant + Neo4j + Postgres update)
      └─► other categories (letter, receipt, record)
            └─► OCR + structure (no reference_data match)
            └─► persist
```

**Stage modules (cloud/) — all built:**
- `classifier/` — rules-first + OpenRouter LLM fallback ✅
- `ocr/` — proactive router + `tiers/{tesseract,vlm}` + `page_type.py` + consumer ✅
- `structure/` — regex + LLM entity extraction (identity pages) ✅
- `match/` — verified-exact registry match ✅
- `persist/` — Qdrant + Neo4j + Postgres writers ✅
- `retrieval/` — `find_pages(owner × page_type)` ✅
- `dashboard/` — JSON `/api/*` for the Next.js SPA ✅

---

## 9. Shared Libraries

| Module | Purpose |
|---|---|
| `shared/config.py` | All env vars via pydantic-settings; single import |
| `shared/hashing.py` | `compute_sha256(path) → str`; streaming, handles large PDFs |
| `shared/storage_s3.py` | Async S3 client; `put_if_absent` checks before upload |
| `shared/logging.py` | structlog; JSON in prod, coloured console in dev |
| `shared/exceptions.py` | `PipelineError → IngestError, OCRError, PersistError, ManifestError, …` |
| `shared/db.py` | `get_engine()`, `session_scope()` async context manager |
| `shared/qdrant_client.py` | `get_qdrant()`, `ensure_collection(name, size, distance)` |
| `shared/neo4j_client.py` | `get_driver()`, `session_scope()`, `ensure_constraints()` |

---

## 10. Initialisation Scripts

All scripts in `scripts/` are **idempotent** and safe to re-run.

| Script | Does |
|---|---|
| `init_postgres.py` | Verifies tables + columns exist (schema applied by docker-entrypoint) |
| `init_minio.py` | Creates `documents` bucket if absent |
| `init_qdrant.py` | Creates `document_pages` collection if absent (384-dim Cosine) |
| `init_neo4j.py` | Applies 3 UNIQUE constraints + 1 composite index |
| `init_sqs.py` | Creates the local elasticmq FIFO queue (`ocr-pages.fifo`) |
| `init_all.py` | Runs all in order; non-zero exit on any failure |
| `load_reference_data.py` | Bulk-loads Excel → `reference_data` (92,389 rows loaded; per-chunk tx, `ON CONFLICT` resume) ✅ |

Run order: Postgres → MinIO → Qdrant → Neo4j → SQS.

---

## 11. Configuration & Environment

All configuration lives in `shared/config.py` via `pydantic-settings`. Values are read from environment variables (or `.env` file in dev).

Key config groups:
- **Database:** `DATABASE_URL`
- **S3:** `S3_ENDPOINT_URL`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- **Qdrant:** `QDRANT_URL`, `QDRANT_COLLECTION`
- **Neo4j:** `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- **OCR:** `OCR_CONFIDENCE_THRESHOLD` (default `70`), `OCR_LANGS` (default `eng+mar+hin`)
- **Preprocess:** `PREPROCESS_DENOISE`, `PREPROCESS_DESKEW`, `PREPROCESS_THRESHOLD`
- **Logging:** `LOG_FORMAT` (`json` | `console`)

---

## 12. Testing Strategy

| Layer | Marker | Needs containers? |
|---|---|---|
| Unit tests | *(default)* | No — all externals mocked |
| Integration tests | `@pytest.mark.integration` | Yes — all 4 services |

```bash
make test                # unit only (fast, offline)
make test-integration    # integration (requires make up + make init)
```

**Coverage targets (per stage):**
- Happy path
- Idempotent re-run (same `document_id`)
- Missing/corrupt manifest
- Low-confidence OCR token path
- Failed reference_data match → manual_review status

---

## 13. Makefile Targets

| Target | Action |
|---|---|
| `make up` | `docker-compose up -d` |
| `make down` | `docker-compose down` |
| `make down-clean` | `docker-compose down -v` (wipes volumes) |
| `make install` | `uv sync --extra dev` |
| `make init` | Run `scripts/init_all.py` |
| `make test` | `pytest` (unit only) |
| `make test-integration` | `pytest -m integration` |
| `make lint` | `ruff check .` |
| `make format` | `ruff format .` |
| `make db-shell` | `psql` into Postgres container |
| `make minio-init` | MinIO bucket setup only |
| `make serve` | uvicorn on :8000 (`/pipeline/notify`, `/retrieve`, `/api/*`) |
| `make upload` | NAS uploader CLI (PDF → S3 + trigger ingest) |
| `make ocr-worker` | Drain elasticmq → `process_page` |
| `make structure DOC=<id>` | Run structure stage for one document |
| `make match DOC=<id>` | Run match stage for one document |
| `make persist DOC=<id>` | Run persist stage for one document |
| `make web-dev` / `web-build` / `web-up` | Next.js dashboard dev / build / container |

---

## 14. Retrieval Design — Lean Ownership Propagation + Indexing Cascade

> **Owner-propagation decided 2026-06-09, shipped 2026-06-10** (`feat/lean-ownership-retrieval`).
> **Retrieval-first transition (3-tier cascade + `cloud/index/`) implemented
> 2026-06-12** on `claude/confident-albattani-b184b8` (16-task plan, not yet
> merged to `main`). Full rationale in TECH_DECISIONS §20. The owner-propagation
> flow below remains the base case; the cascade adds keyword/graph/vector tiers
> on top via a new **index** stage that runs after persist.
>
> **New index stage** (`cloud/index/`, chained from persist consumer →
> `SQS_INDEX_QUEUE_URL`): per-document `summarizer.py` (document/page summaries),
> `keywords.py` (TF-IDF or LLM keyword extraction, mode = `index_keyword_mode`),
> `entities.py` (6-type LLM entity extraction → `index_entities`), `db_writer.py`
> (writes `document_summary`/`page_summary`/`search_keywords`/`index_entities`/
> `index_status`, FIX-029-style guarded status), `neo4j_writer.py` (MERGEs
> summary/keyword/entity data onto existing `Document`/`Page` nodes).
>
> **Retrieval cascade** (`cloud/retrieval/service.py`, `GET /search`):
> `query_parser.py` turns a natural-language query into a `QueryIntent`
> (LLM-first, keyword-split fallback). `service.py` then tries tiers in order
> until `retrieval_min_results` (default 3) hits are found:
> 1. **Keyword tier** — Postgres `search_keywords @> :terms` (JSONB containment).
> 2. **Graph tier** — Neo4j traversal over `Person`/`Entity`/`Page` for
>    structural matches the keyword tier missed.
> 3. **Vector tier** — Qdrant semantic search over identity-page embeddings
>    (existing §5 collection).
>
> `_merge_hits` deduplicates on `document_id`, keeping the first (highest-tier)
> hit. `explainer.py` builds a `RetrievalHit` per result with a tier-specific
> explanation. `GET /search/{doc_id}/pages` returns the page-level detail for a
> hit. A benchmark scaffold (precision@5/recall@5/MRR/top-1) exists with an empty
> `LABELED_QUERIES` list — populate after indexing real bundles.

### Base case: owner × page_type (unchanged)

**The query:** *"the Aadhaar document of Niraj Chopda (+ optional registration number)"* → return the page(s)/PDF.

**The insight:** a practitioner bundle is **one person's** packet. The owner identity (name + permanent `RegistrationNo`) lives on 1–2 **identity pages**. Resolve the owner **once**, propagate it to every page by bundle context. To make an Aadhaar page *findable* we don't need its verbatim text — only (a) what kind of page it is (`page_type`) and (b) whose bundle it belongs to (owner). So retrieval reduces to a **structured filter**, not a vector search.

**Flow** (`cloud/retrieval/service.py → find_pages`, `GET /retrieve`):
```
1. Resolve person:
     exact registration_no  → documents row
     else fuzzy name (rapidfuzz over the SMALL matched-doc set)

2. Filter (verified-owner gate):
     SELECT pages WHERE document.owner = <person>
       AND document.match_status = 'matched'     -- verified owners only
       AND pages.page_type = <requested type>

3. Return: page image S3 key + parent PDF S3 key
```

**Verified-owner gate:** only a `match_status='matched'` document is trusted as a propagation source (Persist preserves `manual_review`, never promotes it). This is what makes "propagate the owner to every page" safe.

**Scope + trade-offs (locked in brainstorm):**

| Decision | Choice | Why |
|---|---|---|
| By-person scope | **Practitioner bundles only** | Single-owner, so propagation covers 100%. Govt letters/record books are multi-owner — out of scope here. |
| Qdrant kept? | **Yes — identity-page text only** | Light semantic backup for unanticipated queries on applicant data (college, qualification, year). The example query needs no vectors. |
| Deep content *inside* a cert/letter page | **Not extracted** | Explicit cost trade-off: queries hinging on free-text buried in a non-identity page are not served. Accepted for the cost/latency win. |

**Cost win:** restricting VLM transcription + structure-LLM to the 1–2 identity pages cuts a 13-page bundle from ~26 paid LLM calls to ~4–6 (**≈75–80% reduction**). Tesseract is local/free, so non-identity pages still get cheap text for typing.

---

## 15. Operations Dashboard

A web dashboard to **monitor + control** the pipeline. **Next.js SPA** (`web/`) over a **FastAPI JSON API** (`cloud/dashboard/api.py`, `/api/*`), mounted on `cloud/app.py`. (Replaced the original DASH-1 HTMX/Jinja UI, cut over 2026-06-09.)

| Area | Detail |
|---|---|
| **Auth** | Signed-cookie sessions (stdlib HMAC over `SESSION_SECRET`); credentials in `dashboard_users` (bcrypt). Seed via `scripts/add_dashboard_user.py`. |
| **Monitor** | Document list w/ stage status; doc/page detail (inspect `raw_text`, `structured_json`, classification, S3 page image, reference match); match-rate KPIs + metric bars; `audit_log` view w/ filters; live status via SSE (SELECT-only poll-diff). |
| **Control** | Trigger ingest (wraps `/pipeline/notify`); idempotent stage re-drive (re-classify, requeue OCR). Control actions write one `audit_log` row and **never 500** (return an HTMX/JSON toast). |
| **Isolation** | `queries.py` SELECT-only; `actions.py` only re-drives existing entry points. |
| **Eval lab (DASH-3)** | `/eval` route: enrol uploaded pages → label typed/handwritten → score + threshold sweep (`cloud/eval/content_type.py`, pure arithmetic over stored CV features). NEVER auto-writes thresholds — operator hand-applies the recommendation to triage defaults. Built to UNBLOCK the "triage over-classifies handwritten" calibration (no blind threshold edits). |

DASH-2 cost tracking implemented via Engine Room v2 (`cloud/engine_room/cost_tracking.py`). `cost_events` table exists; `GET /api/engine/costs/summary` returns per-stage + per-run breakdown.

---

## 16. Phase 2 Intelligence Layer

Seven features built TDD-first (tests before code), all passing. These add **observability, self-healing, and operator assistance** to the core pipeline without changing the hot-path ingest→classify→OCR→structure→match→persist→index→retrieve flow.

### 16.1 Human Corrections Learning Loop

**What:** When a reviewer fixes an AI mistake (wrong page type, misread name, incorrect match), the system records the correction and learns from it.

**Schema:** `human_corrections` table (document_id, page_num, correction_type, original_value, corrected_value, ai_confidence, username, ts). Indexed by type, document, and username.

**API:**
- `POST /api/corrections` — record a correction (auth-gated)
- `GET /api/corrections` — list recent corrections
- `GET /api/corrections/analyze` — extract patterns (page-type substitution map, name variation rules, optimal match threshold)
- `POST /api/eval/correct` — evaluation endpoint that auto-records corrections for audit

**Nightly script:** `scripts/apply_corrections.py` runs `analyze_corrections()` and outputs a JSON report of learned patterns. In a future phase this will auto-apply keyword rules, OCR substitution maps, and match thresholds.

**Tests:** 11 tests (`test_corrections.py`) covering store, get, analyze, and API endpoints.

### 16.2 AI-Generated Document Narratives

**What:** Generates a plain-English summary of a document's journey through the pipeline — what was found, what was uncertain, what a reviewer did.

**Service:** `cloud/narratives/service.py` — template-based generation from structured data (match status, page types, identity fields, OCR quality, reviewer actions). No LLM call; pure string templating for speed and determinism.

**API:** `GET /api/documents/{document_id}/narrative` — returns a paragraph summary.

**Tests:** 8 tests (`test_narratives.py`) covering matched, manual-review, failed, and no-identity cases.

### 16.3 AI Context Sidebar

**What:** When a reviewer opens a document, the sidebar shows **cross-referenced intelligence** from the full database — not just the current document.

**Service:** `cloud/context/service.py` — cross-reference DB queries:
- How many times this registration number appears across all documents
- Other applicants with similar names (fuzzy match over registry)
- Applicants from the same college / graduation year
- Gender distribution by year and college

**API:** `GET /api/documents/{document_id}/context` — returns structured context data.

**Tests:** 7 tests (`test_context.py`) covering all query paths and missing-document cases.

### 16.4 Predictive Self-Healing Pipeline

**What:** The pipeline detects its own failures and **fixes itself** without human intervention, using only smarter error handling (no extra infrastructure).

**Modules:** `cloud/self_healing/`
- `patterns.py` — detects known name variations (middle-name omitted, initials, transliteration) from `human_corrections` and `reference_data` history. If a name mismatch is a known variation, auto-accepts the match.
- `identity_search.py` — finds "hidden" identity pages misclassified as `other`. Re-runs page-type classification on low-confidence pages; if a page contains identity keywords (name, DOB, reg-no), reclassifies it and re-queues for structure extraction.
- `monitor.py` — detects stuck documents (`processing` or `structuring` status older than 30 min). Auto-resumes: if all pages are OCR-done, re-queues structure; if structure is done, re-queues match.
- `retry.py` — per-page OCR retry with escalation: rotation → de-skew → contrast; blur → sharpen; if Tesseract fails 3×, escalates to VLM. Max 3 attempts per issue.

**Tests:** 13 tests (`test_self_healing.py`) covering all four modules.

### 16.5 Identity Intelligence (v1)

**What:** Cross-page consistency checks for practitioner bundles. Compares name, DOB, and registration number across all identity pages and computes an overall consistency score.

**Service:** `cloud/identity/intelligence.py` — per-field consistency checks with weighted scoring:
- Name: exact match = 1.0, middle-name omitted = 0.9, initials = 0.85, different person = 0.0
- DOB: exact match = 1.0, format variation = 0.95, mismatch = 0.0
- Registration number: match = 1.0, missing = 0.5, mismatch = 0.0
- Overall score: weighted average (name 40%, DOB 30%, reg_no 30%)

**API:** `GET /api/documents/{document_id}/identity` — returns per-page and overall consistency report.

**Tests:** 11 tests (`test_identity.py`) covering perfect match, variations, inconsistency, and API endpoints.

### 16.6 Dynamic Cost Router (v1)

**What:** Predicts per-page OCR failure probability **before** running OCR, and routes to the cheapest tier that will still succeed.

**Service:** `cloud/ocr/cost_router.py` — rule-based failure prediction from page features:
- `content_type` (typed/handwritten/mixed)
- `page_type` (form/cert/letter/etc.)
- Historical corrections for this page type
- Handwriting density heuristic

Prediction buckets: `high` (≥0.7 failure prob) → skip Tesseract, go straight to VLM; `low` (<0.3) → Tesseract-only; `medium` → normal ladder.

**Integration:** Gated by `cost_router_enabled` setting in `cloud/ocr/router.py`. When enabled, `_start_index` calls `route_with_prediction()` before OCR.

**Tests:** 6 tests (`test_cost_router.py`) + 16 existing router tests still pass.

### 16.7 Engine Room (v2)

**What:** A real engineer control panel for tuning pipeline parameters, running A/B tests, and tracking costs per stage.

**Schema:** `tuning_parameters` table (merged into `db/schema.sql`) — name, value, previous_value, changed_by, changed_at, reason.

**Modules:** `cloud/engine_room/`
- `tuner.py` — `get_parameters()`, `set_parameter()`, `test_parameter()` on a sample of documents
- `ab_test.py` — `run_ab_test()` comparing baseline vs variant on a sample
- `cost_tracking.py` — `get_cost_summary()` aggregating `cost_events` by stage and run

**API endpoints (`/api/engine/*`, admin-only):**
- `GET /api/engine/parameters` — list all tuning parameters
- `POST /api/engine/parameters/{name}` — update a parameter
- `POST /api/engine/parameters/test` — test a parameter value on sample docs
- `POST /api/engine/ab-test` — run an A/B test
- `GET /api/engine/costs/summary` — cost breakdown per stage and per run

**Tests:** 6 tests (`test_engine_room_v2.py`) covering all endpoints and auth gating.

---

## 17. Production Migration Path

| Component | Dev | Prod |
|---|---|---|
| Blob storage | MinIO (local) | AWS S3 |
| Pipeline trigger | HTTP POST shim | S3 event → SQS → Lambda |
| Local queue | elasticmq (Docker) | AWS SQS (FIFO) |
| Cloud OCR (VLM tier) | OpenRouter (`google/gemini-2.5-flash`) | OpenRouter (same) — single `OPENROUTER_API_KEY` |
| Postgres | Docker container | RDS (Aurora Postgres) |
| Qdrant | Docker container | RDS pgvector (in-Postgres, 384-dim cosine) |
| Neo4j | Docker (APOC) | Amazon Neptune Serverless (openCypher) |
| Process orchestration | Single process | Lambda per stage or Step Functions |

---

## 18. Open Items & Known Gaps

> Pipeline is complete end-to-end and validated on a real 13-page bundle (all 4
> datastores clean). The table below is what remains, not what's missing in the core flow.

| Item | Priority | Notes |
|---|---|---|
| **Measure FIX-048 cost savings** | High | Image resize (768px) for classify VLM deployed 2026-06-15; awaiting live pipeline run to confirm token count reduction. Expected: $0.069→$0.007–0.017 per 13-page bundle. |
| **Merge retrieval-first transition to `main`** | High | `claude/confident-albattani-b184b8` (16 tasks, 45 unit green) — `cloud/index/`, `cloud/retrieval/{query_parser,explainer}.py`, `GET /search` + `GET /search/{doc_id}/pages`. Needs PR + merge. |
| **Wire index stage end-to-end** | High | Add `SQS_INDEX_QUEUE_URL` to `.env`; run `python -m scripts.apply_index_schema` once against live DB (adds `document_summary`/`page_summary`/`search_keywords`/`index_entities`/`index_status` + GIN index). Persist consumer already chains to it post-merge. |
| **AWS auto-trigger wiring** | High | Structure→Match→Persist→Index chaining (Lambda-per-stage+SQS vs Step Functions UNDECIDED); Lambda container images for Tesseract/OpenCV/PyMuPDF; Terraform vs SAM/CDK. The next pipeline milestone. |
| **Populate `LABELED_QUERIES`** for retrieval benchmark | Medium | Benchmark scaffold exists (precision@5/recall@5/MRR/top-1), marked `skip`. Populate after indexing real bundles. |
| **Triage calibration** (over-classifies `handwritten`) | Medium (de-risked, FIX-035 closed) | AND-logic thresholds (h_cv≥1.10 / s_cv≥1.80) calibrated on real scans 2026-06-11; one-metric-over → UNKNOWN → Tesseract. Eval lab (DASH-3) still useful for fine-tuning with more labeled data. |
| **Match fuzzy thresholds** uncalibrated | Medium | `FUZZY_MATCH_HIGH=90`/`FUZZY_REVIEW_LOW=65`/`NAME_CONFIRM=85`/`NAME_CONFLICT_FLOOR=60` (revised 2026-06-11/12) — still no labeled pairs. |
| Wire `OPENROUTER_API_KEY` | Medium | Confirmed live 2026-06-12 (test call OK); sole cloud-OCR/LLM credential. Default text model is `openrouter/free` (FIX-037, auto-routing). |
| Manual dashboard smoke | Medium | Not yet run end-to-end: needs `make up` + `make serve` + `make web-dev` + seeded user (`scripts/add_dashboard_user.py`). |
| Historical re-OCR queue for old `page_type="cover"` manifests | Low | One-off: pages OCR'd before FIX-041 still carry pre-`form` typing; Task 6's cover→VLM-first fix only applies going forward. Not a regression. |
| Push `main` to origin | Low | `main` is local-only, ahead of origin by many commits (user's choice). |
| DASH-2 (cost/usage tracking) | ✅ Done | Implemented via Engine Room v2 (`cloud/engine_room/cost_tracking.py`). `cost_events` table already existed; `get_cost_summary()` aggregates by stage and per run. `GET /api/engine/costs/summary` returns breakdown. |
| Multi-owner by-person retrieval (letters/record books) | Low | Out of current scope (single-owner practitioner bundles only); a heavier per-mention path if ever needed. §14. |
| Neo4j `Organization` + `Vendor` nodes | Low | For letter/receipt pipelines. |
| Heavy dep split (torch/sentence-transformers) | Low | ~2GB install; revisit before Lambda packaging. |
| Pre-commit hooks; residual ruff debt in classifier/ingest/ocr/nas | Low | Deferred (pre-existing, out of scope of recent stages). |

**Done since v1.0** (was TBD, now built): `load_reference_data` (92K rows), `cloud/{classifier,ocr,structure,match,persist,retrieval}/`, NAS uploader + local elasticmq end-to-end, schema (`queued` status, `app_no` BIGINT, `eval_content_type`, `page_types` tables), Next.js dashboard + JSON API + eval lab, NAS-side page-type detection (FIX-041 — `shared/page_type.py`).

**Done since v2.0 (2026-06-12 session):** 12 pipeline-accuracy fixes (reg_no length cap, `app_cover` retirement, cover→VLM-first, registry back-fill with `ocr_extracted` audit trail, FUZZY_REVIEW_LOW 75→65, DOB ±1day fuzzy), bare `R-NNNNN` regex (FIX-037-bare), full `cloud/index/` + `cloud/retrieval/` 3-tier cascade (16 tasks, merged to `main`), NAS-side `classify_page_type` → manifest `page_type="form"` (FIX-041). 3-bundle re-validation: all `matched`.

**Done since v2.2 (2026-06-16 session):** Phase 2 Intelligence layer — all 7 features TDD-complete with 62 tests green: Human Corrections Learning Loop (`cloud/corrections/` + `scripts/apply_corrections.py` + `human_corrections` table), AI-Generated Document Narratives (`cloud/narratives/`), AI Context Sidebar (`cloud/context/`), Predictive Self-Healing Pipeline (`cloud/self_healing/` — patterns, identity search, monitor, retry), Identity Intelligence v1 (`cloud/identity/intelligence.py` — cross-page consistency), Dynamic Cost Router v1 (`cloud/ocr/cost_router.py` — rule-based failure prediction), Engine Room v2 (`cloud/engine_room/` — parameter tuner, A/B test runner, cost tracking + `tuning_parameters` table). All API endpoints (`/api/corrections`, `/api/documents/{id}/narrative`, `/api/documents/{id}/context`, `/api/documents/{id}/identity`, `/api/engine/*`) live in `cloud/dashboard/api.py`.

## 9. AWS Cloud Infrastructure (Phase 0, 2026-06-16)

### 9.1 Architecture Overview

- **Principle**: Zero Docker in production. All services are AWS managed: S3, SQS, RDS PostgreSQL, ElastiCache Redis, Lambda, ECS Fargate, CloudWatch, Secrets Manager.
- **Region**: `ap-south-1` (Mumbai) — lowest latency for India.
- **Deployment**: SAM CLI for CloudFormation. `Terraform-prod` branch preserves original Terraform for reference.
- **Compute**: Lambda for async pipeline stages (serverless, pay-per-invocation). ECS Fargate for API (always-on, WebSocket-capable).
- **Storage**: S3 for documents/images. RDS PostgreSQL 16 (t3.micro) for data + pgvector. ElastiCache Redis (cache.t4g.micro) for sessions + rate limiting.
- **Messaging**: SQS FIFO queues (ocr → vlm → structure → match → persist). S3 event notifications trigger pipeline. DLQs for all queues.
- **Security**: Secrets Manager (KMS-encrypted). IAM least-privilege. VPC security groups. CloudTrail audit logging.
- **Monitoring**: CloudWatch dashboard + 4 alarms. Custom metrics: queue depths, latency, error rates, cost per doc.
- **Cost**: ~$89/month base + ~$6 per 200-document batch.

### 9.2 SAM Template Resources

- **S3**: Bucket with event notification (`s3:ObjectCreated:*` on `manifest.json`) → SQS `ocr-queue.fifo`.
- **SQS**: 5 FIFO queues (ocr, vlm, structure, match, persist) + DLQs. 14-day retention, 5-minute visibility timeout, 1-day message retention, max 10,000 in-flight messages.
- **RDS**: PostgreSQL 16, t3.micro, 20GB gp2, Multi-AZ disabled, automated backups 7 days, `pg_trgm` + `pgvector` extensions.
- **ElastiCache**: Redis 7, cache.t4g.micro, cluster mode disabled, 3-day snapshot retention, no-multi-AZ.
- **Lambda**: 6 functions (OCR, VLM, Structure, Match, Persist, Index). Python 3.13, 2048MB memory, 15 min timeout, 10 concurrency. Environment variables: queue URLs, S3 bucket, region, secrets ARN. DLQ for all. Dead letter config.
- **ECS Fargate**: Service "api", 1 task (1 CPU / 2GB), FARGATE:FARGATE_SPOT weighted 3:1, desired count 1, health check grace 60s, deployment circuit breaker enabled, CloudWatch logging.
- **ALB**: Internet-facing, HTTP (80), target group `api-tg`, health check `/api/health`, 30s interval, 5s timeout, 2 healthy / 3 unhealthy thresholds.
- **CloudWatch**: Dashboard with 8 widgets (queue depths, lambda errors, processing latency, cost per doc, DB connections, Redis memory, API latency, document throughput). 4 alarms: queue depth, error rate, API latency, cost threshold.
- **Secrets Manager**: Single secret `docintel-{env}/credentials`, KMS-encrypted, auto-rotation disabled. Stores: DB password, Redis password, LLM API key, VLM API key, Tesseract API key, JWT secret, admin password.
- **IAM**: 6 Lambda roles (least-privilege), ECS task role, ECS execution role, deploy user (CloudFormation + SAM + ECR).
- **VPC**: Security groups for RDS (port 5432, no public IP), ElastiCache (port 6379, no public IP), ALB (port 80), ECS tasks (all outbound).

### 9.3 Deploy/Destroy Scripts

- **deploy.py**: One-command interactive deploy. Steps: validate prereqs (SAM CLI, AWS CLI, Docker), prompt for VPC/subnets (default VPC auto-detected), prompt for external credentials (LLM, VLM, Tesseract), create `samconfig.toml` or run `sam deploy`, output all endpoints, save to `docintel-{env}-outputs.json`. Non-interactive mode: `--non-interactive` reads from env vars.
- **destroy.py**: One-command teardown. Steps: confirm, destroy non-retained resources (S3 objects, then CloudFormation stack), full deletion ~20 min. S3 bucket retained for safety (empty + manual delete).

### 9.4 NAS Upload Agent

- **File**: `nas/upload_agent.py` — zero-Docker, Python-only.
- **Pipeline**: Render PDF → Preprocess image → Classify page → Upload to S3 → Upload manifest.json (triggers pipeline).
- **Render**: PyMuPDF, 300 DPI, max dimensions 4096×4096, PNG format.
- **Preprocess**: OpenCV — grayscale, denoise, deskew, adaptive threshold.
- **Classify**: Tesseract OCR + keyword-based matching (marks, certificate, internship, letter, application, exam, score, transcript, ID, photo, signature, stamp, fee, receipt, challan).
- **Upload**: S3 `s3://{bucket}/uploads/{timestamp}/{category}/{filename}/{page_num}.png` + `manifest.json` LAST.
- **Batch**: asyncio.Semaphore(workers) for concurrent uploads. Category: "practitioner" (default) or other.
- **Makefile targets**: `upload-aws` (single PDF), `upload-aws-batch` (folder).

### 9.5 Lambda Stubs (Phase 0)

- **6 functions**: OCR, VLM, Structure, Match, Persist, Index.
- **Pattern**: `lambda_handler(event, context)` → parse SQS records → log receipt → return `{"batchItemFailures": []}`.
- **Phase 1**: Replace stub bodies with actual imports from `cloud/{ocr,structure,match,persist,index}`. Each handler will import the relevant service, call it with S3 object key, and push result to next SQS queue.
- **Error handling**: Partial batch responses (`batchItemFailures`) for retry. DLQ for permanent failures.
- **Cold starts**: ~1-2s per stage. Acceptable for async processing. Provisioned Concurrency considered for high-volume stages.

### 9.6 AWS Client Factories

- **File**: `shared/aws_clients.py`.
- **Pattern**: `@lru_cache(maxsize=1)` singleton. Lazy initialization. Config: max_pool_connections=50, retries max_attempts=3 adaptive mode.
- **Services**: S3, SQS, Secrets Manager, CloudWatch, ECS, RDS, ElastiCache.
- **Auth**: Local dev — env vars + endpoint URLs. Production — IAM role (no credentials in code).
- **Config**: `shared/config.py` extended with AWS fields. `database_url` property auto-falls-back from RDS to local.

### 9.7 Makefile AWS Targets

- `aws-deploy` — Interactive deploy
- `aws-destroy` — Destroy with confirmation
- `aws-deploy-non-interactive` — Non-interactive deploy (reads env vars)
- `aws-logs-{ocr,vlm,structure,match,persist,index}` — Tail CloudWatch logs for each Lambda
- `aws-sqs-status` — Show all queue depths
- `ecr-login` — Authenticate Docker with ECR
- `build-api` — Build API Docker image
- `push-api` — Push API image to ECR
- `upload-aws` — Upload single PDF via NAS agent
- `upload-aws-batch` — Upload folder of PDFs via NAS agent
- `aws-cost-estimate` — Show cost breakdown

### 9.8 Phased Roadmap (from REIMAGINING_GROUNDED.md)

- **Phase 0 (Infrastructure)** ✅: SAM template, deploy/destroy scripts, Lambda stubs, NAS upload agent, config updates, Makefile targets. COMPLETE.
- **Phase 1 (TDD Pipeline)** ✅: Replace Lambda stubs with actual imports. Build API Docker image. Deploy to Vercel. WebSocket real-time. Aether chat v1. Engine Room v1. Estimated 2–3 weeks. **COMPLETE — all 7 Phase 2 intelligence features built TDD-first (62 tests).**
- **Phase 2 (Intelligence Layer)** ✅: Human Corrections Learning Loop, AI Narratives, AI Context Sidebar, Predictive Self-Healing Pipeline, Identity Intelligence v1, Dynamic Cost Router v1, Engine Room v2. COMPLETE.
- **Phase 3 (Vercel + Polish)**: Next.js deploy to Vercel. Frontend polish. Cost dashboard. Advanced Aether features. Estimated 2 weeks.
- **Phase 4 (Advanced)**: Multi-tenant. Batch processing. Export formats. Advanced matching. Admin dashboard. Estimated 3 weeks.
- **Phase 5 (Scale)**: CDN. Caching. Performance optimization. Multi-region. Estimated 2 weeks.
- **Total estimated**: 9–10 weeks for full production deployment.

### 9.9 Design Philosophy (Reimagining)

- **Warm Editorial Minimalism**: Inspired by Linear, Notion, Perplexity, Apple. Clean typography, generous whitespace, subtle warm tones, progressive disclosure.
- **Accessibility-first**: WCAG 2.1 AA minimum, semantic HTML, ARIA labels, keyboard navigation, screen reader support, reduced motion, high contrast mode.
- **AI-native workspace**: Not a chat interface bolted onto a traditional app. Aether is a first-class omniscient interface that can answer questions, take actions, and learn from user behavior.
- **Engineer-first**: Engine Room is a real control panel for engineers, not a marketing dashboard. Shows actual pipeline state, costs, errors, and allows real-time intervention.
- **Self-healing pipeline**: Pipeline detects its own failures, retries with exponential backoff, and escalates to humans only when necessary. Cost-neutral: no extra infrastructure, just smarter error handling.
- **Dynamic cost routing**: Game theory-based cost optimization. Routes to cheaper models when quality is sufficient, more expensive models when accuracy is critical. No rigid model tiers.
- **Document autopsy**: Text-only deep dive into why a document failed. No heatmaps, no 3D visualization. Just clear, structured analysis of what went wrong and how to fix it.
- **Learning from corrections**: Every human correction feeds back into the model. Feedback loop is automatic, not manual. Quality improves over time without explicit retraining.
