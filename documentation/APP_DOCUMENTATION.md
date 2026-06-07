# Document Intelligence Pipeline — Full Application Documentation

> **Version:** 1.0 · **Last updated:** 2026-05-17 · **Status:** Active development

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
   - 5.4 OCR
   - 5.5 Confidence Handling
   - 5.6 Structure
   - 5.7 Persist
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
14. [Retrieval Design](#14-retrieval-design)
15. [Production Migration Path](#15-production-migration-path)
16. [Open Items & Known Gaps](#16-open-items--known-gaps)

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
│   ├── storage_s3.py               # Async S3/MinIO client, put_if_absent
│   ├── logging.py                  # structlog JSON/console setup
│   ├── exceptions.py               # Stage-specific exception hierarchy
│   ├── db.py                       # Async SQLAlchemy engine + session_scope
│   ├── qdrant_client.py            # get_qdrant(), ensure_collection()
│   └── neo4j_client.py             # get_driver(), session_scope(), ensure_constraints()
│
├── nas/                            # Runs on the local NAS box
│   ├── preprocess/                 # Image preprocessing (OpenCV, Pillow)
│   ├── manifest/
│   │   └── models.py               # Manifest + PageManifest pydantic v2 models
│   └── uploader/                   # S3 upload agent + HTTP notify shim
│
├── cloud/                          # Runs on AWS (EC2 or Lambda)
│   ├── ingest/
│   │   ├── service.py              # handle_manifest() entry point
│   │   └── storage_db.py           # DocumentRepository + PageRepository
│   ├── classifier/                 # (TBD) doc category + routing
│   ├── ocr/                        # Tesseract + fallback
│   ├── structure/                  # Layout analysis + entity extraction
│   └── persist/                    # Qdrant + Neo4j + S3 writes
│
├── scripts/
│   ├── init_postgres.py
│   ├── init_minio.py
│   ├── init_qdrant.py
│   ├── init_neo4j.py
│   ├── init_all.py
│   └── load_reference_data.py      # (TBD) Excel → reference_data bulk load
│
├── tests/
│   ├── conftest.py
│   ├── shared/
│   │   ├── test_hashing.py
│   │   └── test_integration.py     # @pytest.mark.integration (4 services)
│   ├── nas/
│   └── cloud/
│       └── test_storage_db.py
│
├── docs/
│   └── INTEGRATION.md              # Service deep-dive + troubleshooting
│
├── documentation/                  # ← You are here
│   ├── APP_DOCUMENTATION.md
│   └── TECH_DECISIONS.md
│
├── db/
│   └── schema.sql                  # Postgres DDL (authoritative)
├── docker-compose.yml
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
│      ├─► Classify document bundle (practitioner | letter | …)  │
│      │                                                          │
│      ├─► For each page:                                         │
│      │       OCR (Tesseract eng+mar+hin)                        │
│      │         └─► Low confidence? → LLM fallback              │
│      │       Structure: layout blocks → entity extraction       │
│      │       Embed page text → Qdrant upsert                   │
│      │                                                          │
│      ├─► Match practitioner docs against reference_data         │
│      │       (fuzzy match on RegistrationNo / name+dob)        │
│      │                                                          │
│      └─► Persist: Postgres + Qdrant + Neo4j                    │
│                                                                 │
└───────────────────────────────────────┬─────────────────────────┘
                                        │
          ┌─────────────────────────────┼────────────────────────┐
          ▼                             ▼                        ▼
       Postgres                      Qdrant                   Neo4j
   (metadata + match            (384-dim semantic          (graph: Document
    status + JSONB)              embeddings, page           → Page → Person
                                  + entity level)           → Entity)
```

### Trigger Flow (dev vs prod)

| Environment | Trigger |
|---|---|
| **Dev** | `HTTP POST /pipeline/notify` from NAS uploader after manifest upload |
| **Prod** | S3 `s3:ObjectCreated` on `manifest.json` → SQS → Lambda → `handle_manifest()` |

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
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

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

### 5.4 OCR

**Responsibility:** Extract text + per-word confidence + bounding boxes from each page image.

**Primary:** Tesseract via `pytesseract.image_to_data(output_type=DICT)`
- Language pack: `eng+mar+hin`

**Fallback (low-confidence pages):** Qwen / Gemma VLM (local on NAS during dev; Lambda-hosted in prod)

**Output per word:**
```json
{ "text": "Ashish", "conf": 87.3, "bbox": [x, y, w, h], "page_num": 1 }
```

---

### 5.5 Confidence Handling

**Threshold:** 70 (default; configurable via `OCR_CONFIDENCE_THRESHOLD`)

**For tokens below threshold:**
1. Fuzzy-match surrounding extracted context against `reference_data` table using `rapidfuzz`.
2. If match found → substitute value, tag `source: augmented`.
3. If no match → flag token for `manual_review` queue; set page `match_status = manual_review`.

---

### 5.6 Structure

**Responsibility:** Convert per-page OCR `raw_text` into structured entities,
refine each page's `page_type`, and roll up the document-level practitioner
identity.

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

**Trigger:** `scripts/run_structure.py --document-id X` (per-document; rollup
needs every page OCR'd). Auto-trigger on OCR-complete is deferred to AWS wiring.

---

### 5.7 Persist

**Qdrant:**
- Collection: `document_pages` | Vector: 384-dim Cosine | Model: `paraphrase-multilingual-MiniLM-L12-v2`
- Upsert at page level + entity level.
- Payload: `document_id`, `page_num`, `entity_types`, key entity values.

**Neo4j:**
- All writes via `MERGE` (idempotent).
- Node types: `Document`, `Page`, `Person`, `Entity`, `Organization` (TBD), `Vendor` (TBD).
- Relationships: `HAS_PAGE`, `MENTIONS`, `BELONGS_TO`, `MATCHES`.
- `Person` merge key: `registration_no` (not name+dob).
- Constraints: `Document.document_id` UNIQUE, `Page.page_id` UNIQUE, `(Person.registration_no)` UNIQUE; index on `(Entity.type, Entity.value)`.

**Postgres:**
- Update `documents.match_status` to `matched` / `manual_review` / `unmatched`.
- Store `reference_data_id` FK when practitioner is matched.

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
  (:Page)-[:MENTIONS]->(:Entity)
  (:Person)-[:BELONGS_TO]->(:Document)
  (:Person)-[:MATCHES]->(:ReferenceData)  ← logical; ref data lives in Postgres
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

**Stage modules (cloud/):**
- `classifier/` — document category detection (rules-first + LLM fallback) ← **TBD**
- `ocr/` — Tesseract wrapper + LLM fallback ← **TBD**
- `structure/` — layout + NER ← **TBD**
- `persist/` — Qdrant + Neo4j + Postgres writers ← **TBD**

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
| `init_all.py` | Runs all 4 in order; non-zero exit on any failure |
| `load_reference_data.py` | Bulk-loads Excel → `reference_data` table ← **TBD** |

Run order: Postgres → MinIO → Qdrant → Neo4j.

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

---

## 14. Retrieval Design

Query: *"documents of Ashish, DOB 26 Feb 1996"*

```
1. Parse query
   → structured: { name: "Ashish", dob: "1996-02-26" }
   → semantic intent: "find practitioner documents"

2. Neo4j filter
   MATCH (p:Person)-[:BELONGS_TO]->(d:Document)
   WHERE p.registration_no IN <candidates from name+dob lookup>
   RETURN d.document_id

3. Qdrant re-rank
   Search within candidate document_id set
   Query vector = embed("Ashish 26 Feb 1996 practitioner")
   Filter: { document_id: { $in: [<neo4j results>] } }

4. Return
   Ranked documents + highlighted matching entities
```

Every storage decision (what gets embedded, what becomes a node, what payload is kept) is made to support this flow without reprocessing.

---

## 15. Production Migration Path

| Component | Dev | Prod |
|---|---|---|
| Blob storage | MinIO (local) | AWS S3 |
| Pipeline trigger | HTTP POST shim | S3 event → SQS → Lambda |
| OCR LLM fallback | Local Qwen/Gemma | Lambda-hosted |
| Postgres | Docker container | RDS (Aurora Postgres) |
| Qdrant | Docker container | Qdrant Cloud or EC2 |
| Neo4j | Docker (APOC) | Neo4j AuraDB or EC2 |
| Process orchestration | Single process | Lambda per stage or Step Functions |

---

## 16. Open Items & Known Gaps

| Item | Priority | Notes |
|---|---|---|
| Schema explicit ack | High | `make down-clean && make up && make init` needed to apply latest DDL |
| `scripts/init_postgres.py` verify update | High | Must check new column names from schema rewrite |
| `init_qdrant.py` model name update | Medium | Change to `paraphrase-multilingual-MiniLM-L12-v2` |
| `scripts/load_reference_data.py` | High | Excel → `reference_data` bulk load not yet built |
| `cloud/classifier/` | High | Doc category detection (rules-first + LLM fallback) |
| `cloud/ocr/` | High | Tesseract wrapper + fallback |
| `cloud/structure/` | High | Layout analysis + NER |
| `cloud/persist/` | High | Qdrant + Neo4j + Postgres writers |
| Neo4j `Organization` + `Vendor` nodes | Medium | Needed for letter/receipt pipelines |
| Blank page skip logic | Medium | Pixel-variance threshold value TBD |
| Heavy dep split (torch/sentence-transformers) | Low | Currently ~2GB install; consider optional extras |
| Pre-commit hooks | Low | Deferred |
| Ops/control dashboard — DASH-1 (operational) | Planned | FastAPI + HTMX/Jinja in new `cloud/dashboard/` pkg. Monitor + control (doc/stage status, inspect outputs, trigger ingest, idempotent stage re-drive, match-rate) + basic auth + `audit_log` table. Ready to build (reads existing state). See TECH_DECISIONS §19. |
| Ops/control dashboard — DASH-2 (cost tracking) | Planned | Add `ocr_tier` to `pages`; instrument OCR tiers + `classifier/llm.py` → new `cost_events` table; cost views. Blocked on that plumbing. TECH_DECISIONS §19. |
| Ops/control dashboard — DASH-3 (accuracy eval lab) | Planned | Ground-truth store + eval runner (OCR/classification accuracy, T1/T2/T3 tier comparison). Blocked on ground-truth data. TECH_DECISIONS §19. |
