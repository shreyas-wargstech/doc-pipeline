# Integration Guide — Zero to 100%

From "fresh clone" to "all four data stores wired, verified, and ready for pipeline stages."

Covers **Postgres**, **MinIO (S3)**, **Qdrant**, **Neo4j** — the four data stores behind the document pipeline.

If anything fails, jump to [Troubleshooting](#troubleshooting).

---

## 1. What you're integrating

```
                ┌─────────────────┐
                │  Pipeline code  │
                └────────┬────────┘
        ┌───────┬────────┼────────┬────────┐
        ▼       ▼        ▼        ▼        ▼
    Postgres   S3      Qdrant    Neo4j   (Tesseract,
    (state)  (blobs) (vectors) (graph)    embeddings — local libs)
```

| Store    | Holds                                            | Used by stage         |
|----------|--------------------------------------------------|-----------------------|
| Postgres | document/page status, Excel ground truth         | ingest, persist       |
| S3       | original PDFs, page PNGs, `manifest.json`        | ingest, NAS uploader  |
| Qdrant   | page-level + entity-level embeddings             | persist, retrieval    |
| Neo4j    | Document/Page/Person/Entity nodes + relationships| persist, retrieval    |

All four are **idempotent on natural keys** — re-running any stage on the same `document_id` produces no duplicate writes.

---

## 2. Prerequisites

- **Docker** (with `docker compose` v2)
- **Python 3.11+**
- **uv** for dep management — `pip install uv` if you don't have it
- **~5 GB free disk** for Docker volumes + Python deps (`sentence-transformers` pulls torch)

Verify:
```bash
docker compose version
python --version          # 3.11+
uv --version
```

---

## 3. The 5-step quickstart

```bash
# 1. Get deps
make install

# 2. Copy env template (defaults work for local)
cp .env.example .env

# 3. Bring up all four services
make up

# 4. Initialize each (bucket, collection, constraints) — idempotent
make init

# 5. Verify everything by hitting real services
make test-integration
```

That's it. If `make test-integration` is all green, you're at 100%.

The rest of this doc explains **what each step actually does** so you can debug, extend, and migrate to production.

---

## 4. Step-by-step walkthrough

### Step 1 — `make install`

Runs `uv sync --extra dev`. Reads `pyproject.toml`, creates `.venv/`, installs:

- Web/config: `fastapi`, `pydantic`, `pydantic-settings`, `httpx`
- DB: `sqlalchemy[asyncio]`, `asyncpg`, `alembic`
- Object storage: `aioboto3`
- Vector + graph: `qdrant-client`, `neo4j`
- Embeddings: `sentence-transformers` (pulls torch, ~2 GB)
- OCR/image: `pytesseract`, `pymupdf`, `pdf2image`, `opencv-python-headless`, `Pillow`, `scikit-image`
- Matching/NLP: `rapidfuzz`, `spacy`
- Reference data: `pandas`, `openpyxl`
- Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `moto`

First install takes ~5 min on a normal connection. Subsequent runs use the uv cache.

### Step 2 — `cp .env.example .env`

The defaults work for local dev. Only edit if you've changed ports in `docker-compose.yml` or are pointing at real cloud services.

Important variables:

| Variable                   | Local default                       | Prod (real AWS / managed)         |
|----------------------------|--------------------------------------|------------------------------------|
| `DATABASE_URL`             | `postgresql+asyncpg://pipeline:pipeline@localhost:5432/doc_pipeline` | RDS connection string |
| `S3_ENDPOINT_URL`          | `http://localhost:9000` (MinIO)     | **leave blank** for real AWS S3    |
| `S3_BUCKET`                | `documents`                          | your real bucket                   |
| `QDRANT_URL`               | `http://localhost:6333`              | Qdrant Cloud URL                   |
| `NEO4J_URI`                | `bolt://localhost:7687`              | `neo4j+s://...` for AuraDB         |
| `OCR_CONFIDENCE_THRESHOLD` | `70`                                 | tune per document set              |

### Step 3 — `make up`

Runs `docker compose up -d`. Starts four containers:

```
docpipe-postgres   :5432              postgres:16-alpine
docpipe-minio      :9000, :9001       minio/minio:latest
docpipe-qdrant     :6333, :6334       qdrant/qdrant:latest
docpipe-neo4j      :7474, :7687       neo4j:5-community + APOC
```

**What happens at first boot:**

- **Postgres** mounts `./db/schema.sql` into `/docker-entrypoint-initdb.d/`. On the **first** container start (empty data volume), it auto-runs the schema. Subsequent starts skip it.
- **MinIO**, **Qdrant**, **Neo4j**: start empty. We seed them in step 4.

Verify all four are up:
```bash
docker compose ps
# All should show "running" or "running (healthy)"
```

If Postgres or Neo4j say `starting`, wait 10–15 s and re-check.

### Step 4 — `make init`

Runs `python -m scripts.init_all`. Executes four idempotent scripts in order:

| # | Script              | What it does                                                          | Idempotent because…                  |
|---|---------------------|-----------------------------------------------------------------------|--------------------------------------|
| 1 | `init_postgres.py`  | Queries `information_schema.tables`, verifies `documents`, `pages`, `reference_data` exist | Read-only check; fails loud if missing |
| 2 | `init_minio.py`     | `head_bucket` first; `create_bucket` only if 404                       | Skips create on existing bucket      |
| 3 | `init_qdrant.py`    | `get_collections` first; `create_collection` only if missing           | Skips create on existing collection  |
| 4 | `init_neo4j.py`     | Runs `CREATE CONSTRAINT ... IF NOT EXISTS` for each natural key        | `IF NOT EXISTS` is a no-op if present|

Expected output: each step ends with `init.<name>.ok`, then `init.all.ok`.

Re-run as often as you want.

### Step 5 — `make test-integration`

Runs `pytest -m integration`. Hits all four real services. Tests:

- Postgres connect + expected tables present
- S3 `put_if_absent` is idempotent (uploads first time, skips second)
- Qdrant `ensure_collection` is idempotent + has correct dim
- Neo4j constraints are present + idempotent

If green, the integration substrate is 100% ready for pipeline stages to build on.

---

## 5. Per-service deep dive

### 5.1 Postgres

**Connection:** `postgresql+asyncpg://pipeline:pipeline@localhost:5432/doc_pipeline`

**Schema** (full SQL in `db/schema.sql`):

```
documents          one row per uploaded PDF, PK = document_id (sha256)
pages              one row per page, PK = page_id ('<doc_id>:<page_num>'), FK → documents
reference_data     Excel ground truth, GIN index on fields_norm (JSONB)
```

`updated_at` is auto-maintained via a trigger.

**Client code:** `shared/db.py`

```python
from shared.db import session_scope

async with session_scope() as sess:
    await sess.execute(text("SELECT count(*) FROM documents"))
```

`session_scope` commits on clean exit, rolls back on exception. The engine is module-level cached for long-running services. In tests, build your own engine with `create_async_engine` to avoid event-loop reuse issues.

**Modifying the schema later:** add a new `.sql` file under `db/migrations/` and apply with Alembic (set up in a later session). Don't edit `schema.sql` once you've deployed — the docker-entrypoint script only runs on **first** boot of an empty volume.

**Hands-on:**
```bash
make db-shell
\dt                                         # list tables
\d+ documents                               # describe a table
SELECT * FROM documents LIMIT 5;
SELECT pg_size_pretty(pg_database_size('doc_pipeline'));
```

### 5.2 MinIO (S3-compatible)

**S3 endpoint:** `http://localhost:9000`
**Web console:** `http://localhost:9001`  (login: `minioadmin` / `minioadmin`)
**Bucket:** `documents`

**Key layout** (the contract — every stage assumes this):
```
documents/
└── <document_id>/                      sha256 of original PDF
    ├── original.pdf
    ├── pages/
    │   ├── page_001.png
    │   ├── page_002.png
    │   └── ...
    └── manifest.json                   ← uploaded LAST → triggers cloud pipeline
```

The `manifest.json` schema is defined in `nas/manifest/models.py` and versioned (`schema_version`). The cloud side reads it as its source of truth.

**Client code:** `shared/storage_s3.py`

```python
from shared.storage_s3 import S3Storage

s3 = S3Storage()
uploaded = await s3.put_if_absent("documents/abc.../original.pdf", pdf_bytes)
# uploaded == True if this was the first write, False if already there
data = await s3.get_bytes("documents/abc.../manifest.json")
```

The same code path works against real AWS S3 — just blank `S3_ENDPOINT_URL` in `.env`.

**Hands-on:**
```bash
# Browser at http://localhost:9001 → log in → browse the "documents" bucket
# OR via the mc CLI in another container:
docker run --rm --network host minio/mc \
    alias set local http://localhost:9000 minioadmin minioadmin
docker run --rm --network host minio/mc ls local/documents
```

### 5.3 Qdrant

**HTTP API:** `http://localhost:6333`
**gRPC:** `:6334` (we don't use it; Python client defaults to HTTP)
**Web dashboard:** `http://localhost:6333/dashboard`
**Collection:** `document_pages`

**Collection config (locked):**

| Setting       | Value           | Why                                                                |
|---------------|-----------------|--------------------------------------------------------------------|
| Vector size   | **384**         | `all-MiniLM-L6-v2` output dim                                      |
| Distance      | **Cosine**      | Sentence-transformers outputs are L2-normalized → cosine is correct|
| Payload       | dict per point  | `{document_id, page_num, entity_types, key_fields}`                |

**Trade-off note** — to change embedding model later (e.g. `bge-large` = 1024 dim, or a multilingual model), you must **recreate** the collection with the new dim and re-embed every point. No in-place migration. So pin the model choice before you've embedded a meaningful corpus.

**Client code:** `shared/qdrant_client.py`

```python
from shared.qdrant_client import get_qdrant, ensure_collection

client = get_qdrant()
try:
    await ensure_collection(client)             # idempotent
    # ... upsert points, search, etc.
finally:
    await client.close()
```

**Embedding plan:**
- **Page-level** (default): full OCR text per page → 1 vector → answers "what does this page say?"
- **Entity-level** (optional, future): entity descriptors → answers "find pages mentioning ACME Corp"

**Payload guidance for retrieval:**
Always include `document_id` and `page_num` in payload — those are what Neo4j filters down to. Add `key_fields` (e.g. extracted names, dates) so Qdrant can pre-filter before vector search when the query has structured constraints.

**Hands-on:**
```bash
curl -s http://localhost:6333/collections/document_pages | jq .result.config
curl -s http://localhost:6333/collections/document_pages | jq .result.points_count
```

### 5.4 Neo4j

**Bolt URL:** `bolt://localhost:7687`
**Browser UI:** `http://localhost:7474`  (login: `neo4j` / `pipeline-dev`)
**APOC plugin:** enabled (`apoc.*` procedures available)

**Graph schema (locked):**

| Node       | Natural key       | Properties (typical)                            |
|------------|-------------------|-------------------------------------------------|
| `Document` | `document_id`     | `original_name`, `created_at`                   |
| `Page`     | `page_id`         | `page_num`, `s3_key_image`, `ocr_confidence`    |
| `Person`   | `(name, dob)`     | composite — one node per real person            |
| `Entity`   | indexed `(type, value)` | catch-all for orgs, addresses, IDs etc.   |

| Relationship  | From → To                  | Cardinality | Notes                          |
|---------------|----------------------------|-------------|--------------------------------|
| `HAS_PAGE`    | `Document` → `Page`        | 1 → N       | structural                     |
| `MENTIONS`    | `Page` → `Person` \| `Entity` | N → M    | extracted from OCR text        |
| `BELONGS_TO`  | `Document` → `Person`      | N → M       | document-level ownership       |
| `MATCHES`     | `Document` → `ReferenceRecord` | N → 1   | when an Excel row matched      |

All writes use `MERGE` on natural keys → idempotent.

**Constraints + indexes (applied by `init_neo4j.py`):**

```cypher
CREATE CONSTRAINT document_id_unique FOR (d:Document) REQUIRE d.document_id IS UNIQUE;
CREATE CONSTRAINT page_id_unique     FOR (p:Page)     REQUIRE p.page_id     IS UNIQUE;
CREATE CONSTRAINT person_natural_key FOR (p:Person)   REQUIRE (p.name, p.dob) IS UNIQUE;
CREATE INDEX     entity_lookup       FOR (e:Entity)   ON (e.type, e.value);
```

**Client code:** `shared/neo4j_client.py`

```python
from shared.neo4j_client import session_scope as neo4j_session

async with neo4j_session() as sess:
    await sess.run(
        "MERGE (d:Document {document_id: $id}) SET d.original_name = $name",
        id="abc123...", name="invoice.pdf",
    )
```

**Hands-on (browser at http://localhost:7474):**
```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
MATCH (n) RETURN labels(n) AS label, count(*) AS n;
```

---

## 6. How retrieval will use these (preview)

Target query: *"documents of Ashish, DOB 26 Feb 1996"*

```
1. Parse query        → {name: "Ashish", dob: "1996-02-26"}
2. Neo4j filter       → MATCH (p:Person {name:..., dob:...})<-[:BELONGS_TO]-(d:Document)
                       → returns candidate document_ids: ['abc...', 'def...']
3. Qdrant search      → semantic re-rank within payload filter document_id ∈ candidates
4. Hydrate results    → fetch Document + Page rows from Postgres for display
```

Every storage decision (what to embed, what to put on which node, what payload to keep) supports this flow without re-processing. This is why:
- `document_id` and `page_num` live in **every** Qdrant payload (so filters work)
- `(name, dob)` is a composite Neo4j constraint (so filters are exact, not fuzzy)
- The Postgres `pages.entities` JSONB carries the same data Qdrant embedded (so we can show what matched without a re-OCR)

---

## 7. Daily workflow

| Task                  | Command                  |
|-----------------------|--------------------------|
| Start services        | `make up`                |
| Stop (keep data)      | `make down`              |
| Stop + wipe data      | `make down-clean`        |
| Verify init           | `make init`              |
| Run unit tests        | `make test`              |
| Run integration tests | `make test-integration`  |
| Tail logs             | `make logs`              |
| Postgres shell        | `make db-shell`          |
| Format + lint         | `make format && make lint` |

---

## 8. Troubleshooting

### `make up` fails — port already bound
Another process owns 5432 / 9000 / 6333 / 7687. Either stop it or change the **host** port in `docker-compose.yml` (left side of `"5432:5432"`).

### `init.postgres.missing_tables`
Postgres started but `schema.sql` didn't run. Cause: the data volume already existed from a previous boot, so Postgres skipped the init script.

Fix:
```bash
make down-clean         # wipes volumes
make up
sleep 5                 # wait for Postgres
make init
```

### `init.minio.create_failed` — connection refused
MinIO hasn't finished booting. Wait 5 s and retry, or:
```bash
docker compose logs minio
```

### `init.qdrant.failed` — timeout
You're probably hitting `:6334` (gRPC) instead of `:6333` (HTTP). Check `QDRANT_URL` in `.env`.

### `init.neo4j.failed` — auth failure
The compose file sets the password to `pipeline-dev`. If a previous run used a different password, the volume kept the old creds:
```bash
make down-clean && make up
```

Wait ~20 s for Neo4j to be ready (slower than the other three), then `make init`.

### Integration tests hang
Most likely a service isn't up. Check:
```bash
docker compose ps       # all should be "running"
```

If a service is restarting, `docker compose logs <name>` will show why.

### `ImportError` running scripts directly
Use `python -m scripts.init_xxx` (from project root), not `python scripts/init_xxx.py`. The first form respects package imports; the second doesn't.

---

## 9. What's NOT covered yet (future sessions)

- **Alembic migrations** — for evolving the Postgres schema after deploy
- **DocumentRepository / PageRepository** — idempotent upsert layer over `shared/db.py` (next session per `session_log.md`)
- **Health-check endpoint** — `/healthz` that pings all four integrations
- **AWS deployment path** — Lambda triggers, IAM roles, Secrets Manager for creds
- **Backups** — pg_dump, MinIO mirroring, Neo4j dumps, Qdrant snapshots
- **Connection-pool tuning** — for high-throughput batch ingest

---

## 10. Production migration path

When moving off local Docker, **only `.env` changes**. The code is endpoint-agnostic.

| Service     | Local        | Production candidate                  | Notes                                 |
|-------------|--------------|---------------------------------------|---------------------------------------|
| Postgres    | container    | RDS (Aurora PostgreSQL)               | Use IAM auth or Secrets Manager        |
| MinIO       | container    | S3 (real AWS, same API)               | Blank `S3_ENDPOINT_URL`; use IAM role  |
| Qdrant      | container    | Qdrant Cloud or self-hosted EC2       | Cloud also supports API-key auth       |
| Neo4j       | container    | AuraDB (managed) or self-hosted EC2   | Use `neo4j+s://` URI for TLS           |

Schema migration order (zero-downtime):

1. Apply Postgres schema (Alembic up) — additive only
2. `init_qdrant.py` against new endpoint — collection created empty
3. `init_neo4j.py` against new endpoint — constraints applied
4. Cut over reads/writes to new endpoints in `.env`
5. (Optional) migrate historical data via export/import scripts
