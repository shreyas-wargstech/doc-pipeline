# Document Intelligence Pipeline — Full Application Documentation

> **Version:** 2.0 · **Last updated:** 2026-06-10 · **Status:** Pipeline complete end-to-end (ingest→classify→OCR→structure→match→persist→retrieve); validated on a real 13-page bundle. `main` local-only, ahead of origin.

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
16. [Production Migration Path](#16-production-migration-path)
17. [Open Items & Known Gaps](#17-open-items--known-gaps)

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
├── cloud/                          # Runs on AWS (EC2 or Lambda)
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
│   ├── match/                      # fuzzy.py + reference.py + service.py (verified-exact match)
│   ├── persist/                    # summary.py + embeddings.py + qdrant_writer.py + graph.py + service.py
│   ├── retrieval/                  # service.py — find_pages(owner × page_type)
│   ├── eval/                       # content_type.py — pure threshold-sweep scoring (DASH-3)
│   └── dashboard/                  # api.py (JSON /api/*) + session.py (signed-cookie auth) + sse.py
│                                   #   + queries.py + actions.py + audit.py + eval_queries.py
│
├── web/                            # Next.js dashboard SPA (replaces HTMX) — documents/detail/metrics/audit/eval
│
├── scripts/
│   ├── init_{postgres,minio,qdrant,neo4j,sqs,all}.py
│   ├── load_reference_data.py      # Excel → reference_data bulk load (92,389 rows loaded)
│   ├── apply_migration_001.py      # app_no INTEGER → BIGINT
│   ├── apply_eval_table.py         # idempotent eval_content_type table apply
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
| **Prod** | S3 `s3:ObjectCreated` on `manifest.json` → SQS → Lambda → `handle_manifest()` (auto-trigger chaining structure→match→persist still TODO — see §17). |

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
- Cuts a 13-page bundle from ~26 paid LLM calls to ~4–6.

**VLM tier notes** (`cloud/ocr/tiers/vlm.py`): no per-word confidence — words get a fixed `_CONF_PRIOR = 85.0` (above the 70 net) + `bbox=(0,0,0,0)`. An unavailable VLM on a handwritten page fails cleanly → `manual_review` (NO fall-back to Tesseract, by design). Unavailable START tier **escalates** (`continue`, not `break` — FIX-028).

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
# Literal aliases (single source of truth — OcrPageMessage imports these)
PageType     = Literal["blank", "cover", "form", "receipt", "certificate", "other"]
ContentType  = Literal["typed", "handwritten", "unknown"]      # triage
LanguageHint = Literal["latin", "devanagari", "mixed", "unknown"]  # triage OSD

class PageManifest(BaseModel):
    page_num: int                          # 1-indexed
    s3_key: str                            # documents/<doc_id>/pages/page_NNN.png
    page_type: PageType = "other"          # triage / classifier page label
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
| `metadata` | `JSONB` | category-specific fields |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | auto-managed |

**`pages`**

| Column | Type | Notes |
|---|---|---|
| `page_id` | `TEXT PK` | `<document_id>:<page_num>` |
| `document_id` | `TEXT FK` | → documents |
| `page_num` | `INT` | |
| `s3_key` | `TEXT` | PNG location |
| `page_type` | `TEXT` | triage/classifier label (e.g. cover, form, certificate, blank) |
| `language_detected` | `TEXT` | eng \| mar \| hin \| mixed |
| `ocr_status` | `TEXT CHECK` | pending \| queued \| done \| failed \| skipped |
| `structured_json` | `JSONB` | LLM/OCR structured output |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |

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

## 14. Retrieval Design — Lean Ownership Propagation

> **Decided 2026-06-09, shipped 2026-06-10** (`feat/lean-ownership-retrieval`). Full
> rationale in TECH_DECISIONS §20. This replaces the original "embed every page →
> Neo4j filter → Qdrant re-rank" flow.

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

DASH-2 (cost/usage tracking — needs `ocr_tier` column + token instrumentation → `cost_events`) is still future.

---

## 16. Production Migration Path

| Component | Dev | Prod |
|---|---|---|
| Blob storage | MinIO (local) | AWS S3 |
| Pipeline trigger | HTTP POST shim | S3 event → SQS → Lambda |
| Local queue | elasticmq (Docker) | AWS SQS (FIFO) |
| Cloud OCR (VLM tier) | OpenRouter (`google/gemini-2.5-flash`) | OpenRouter (same) — single `OPENROUTER_API_KEY` |
| Postgres | Docker container | RDS (Aurora Postgres) |
| Qdrant | Docker container | Qdrant Cloud or EC2 |
| Neo4j | Docker (APOC) | Neo4j AuraDB or EC2 |
| Process orchestration | Single process | Lambda per stage or Step Functions |

---

## 17. Open Items & Known Gaps

> Pipeline is complete end-to-end and validated on a real 13-page bundle (all 4
> datastores clean). The table below is what remains, not what's missing in the core flow.

| Item | Priority | Notes |
|---|---|---|
| **AWS auto-trigger wiring** | High | Structure→Match→Persist chaining (Lambda-per-stage+SQS vs Step Functions UNDECIDED); Lambda container images for Tesseract/OpenCV/PyMuPDF; Terraform vs SAM/CDK. The next pipeline milestone. |
| **Triage calibration** (over-classifies `handwritten`) | High | Thresholds (`height_cv .35`/`stroke_cv .45`) uncalibrated on real scans. Eval lab (DASH-3) is BUILT to unblock it — operator enrols+labels real scans → reads recommended thresholds → hand-applies to triage defaults. De-risked (over-classify only escalates to VLM, not fatal). |
| **Match fuzzy thresholds** uncalibrated | Medium | `FUZZY_MATCH_HIGH=90`/`FUZZY_REVIEW_LOW=75` — no labeled pairs yet. |
| Wire `OPENROUTER_API_KEY` | Medium | The sole cloud-OCR credential. Set it to exercise the skipped openrouter integration test. |
| Manual dashboard smoke | Medium | Not yet run end-to-end: needs `make up` + `make serve` + `make web-dev` + seeded user (`scripts/add_dashboard_user.py`). |
| Push `main` to origin | Low | `main` is local-only, ahead of origin by many commits (user's choice). |
| DASH-2 (cost/usage tracking) | Planned | Add `ocr_tier` to `pages`; instrument OCR tiers + `classifier/llm.py` → `cost_events` table; cost views. Blocked on that plumbing. TECH_DECISIONS §19. |
| Multi-owner by-person retrieval (letters/record books) | Low | Out of current scope (single-owner practitioner bundles only); a heavier per-mention path if ever needed. §14. |
| Neo4j `Organization` + `Vendor` nodes | Low | For letter/receipt pipelines. |
| Heavy dep split (torch/sentence-transformers) | Low | ~2GB install; revisit before Lambda packaging. |
| Pre-commit hooks; residual ruff debt in classifier/ingest/ocr/nas | Low | Deferred (pre-existing, out of scope of recent stages). |

**Done since v1.0** (was TBD, now built): `load_reference_data` (92K rows), `cloud/{classifier,ocr,structure,match,persist,retrieval}/`, NAS uploader + local elasticmq end-to-end, schema (`queued` status, `app_no` BIGINT, `eval_content_type` table), Next.js dashboard + JSON API + eval lab.
