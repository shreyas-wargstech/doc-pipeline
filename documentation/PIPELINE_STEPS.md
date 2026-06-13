# Running the Pipeline: Step-by-Step Instructions

This document walks you through the complete pipeline process for processing PDF documents locally.

## Prerequisites

1. **Docker** running and configured
2. **Tesseract OCR** installed with language packs (`eng`, `mar`, `hin`)
3. **Python 3.13.7+** with `uv` package manager
4. **OpenRouter API key** (set in `.env` as `OPENROUTER_API_KEY`)

## Pipeline Architecture Overview

The pipeline has 6 stages:

1. **Upload** — PDF → render pages → upload to S3/MinIO → create manifest
2. **Ingest** — manifest → upsert DB → classify document category → enqueue pages to SQS
3. **OCR** — page image → route tier (Tesseract or VLM) → transcribe → store raw_text
4. **Structure** — raw_text → LLM entity extraction → register entities (reg_no, name, dob, etc.)
5. **Match** — extracted data → fuzzy search vs 92K reference registry → set match_status
6. **Persist** — embeds identity pages to Qdrant + graph to Neo4j + finalize Postgres status

## Full Local Run (5 steps)

### STEP 0: Environment Setup (first time only)

```bash
# Clone/extract repo
cd doc-pipeline

# Install dependencies (dev extras needed for tests + make)
uv sync --extra dev

# Start all Docker services (Postgres, MinIO, Qdrant, Neo4j, ElasticMQ)
make up

# Initialize all databases (schema, buckets, collections, queues)
make init

# Load 92K practitioner reference records from Excel
uv run python -m scripts.load_reference_data

# Verify `.env` has these keys (copy from `.env.example` if missing):
# - OPENROUTER_API_KEY=<your-key>
# - AWS_REGION=us-east-1 (local)
# - SQS_ENDPOINT_URL=http://localhost:9324 (ElasticMQ)
# - SQS_OCR_QUEUE_URL=http://localhost:9324/000000000000/ocr-queue.fifo
# - SQS_STRUCTURE_QUEUE_URL=http://localhost:9324/000000000000/structure-queue.fifo
# - SQS_MATCH_QUEUE_URL=http://localhost:9324/000000000000/match-queue.fifo
# - SQS_PERSIST_QUEUE_URL=http://localhost:9324/000000000000/persist-queue.fifo
```

### STEP 1: Start FastAPI Server (in one terminal)

```bash
make serve
# Listens on http://localhost:8000
# Health check: curl http://localhost:8000/health
```

### STEP 2: Upload PDF (in another terminal)

```bash
# For each PDF, run:
make upload PDF_PATH="<absolute-path-to-pdf>" CATEGORY=practitioner TRIGGER=direct

# Example:
make upload PDF_PATH="C:\Users\Wargstech\Desktop\wargstech\HomoeoFiles_local\AMR-MCH-26-A-07723.pdf" CATEGORY=practitioner TRIGGER=direct
```

The `TRIGGER=direct` flag enqueues the pages to ElasticMQ immediately (no HTTP POST to `/pipeline/notify` needed locally).

**What it does:**
- Renders all pages to PNG (grayscale, no threshold)
- Uploads original PDF + page PNGs to MinIO
- Creates manifest.json with triage info (page_type, content_type, language)
- Enqueues each page to `ocr-queue.fifo` in SQS

### STEP 3: Run OCR Worker (drains the queue)

```bash
# In a separate terminal, run the worker:
make ocr-worker

# Worker processes all enqueued pages:
# - Routes each page (Tesseract T1 or VLM T2)
# - Stores raw_text in structured_json column
# - On success, moves to next stage (structure)
# - On failure, marks page ocr_status=failed, logs error

# Observe: pages.ocr_status in Postgres:
# pending → queued (upload) → done (ocr-worker) → structure/match/persist by sweeper
```

### STEP 4: Run the Orchestration Sweeper (fan-in)

```bash
# In another terminal:
make sweep

# Sweeper watches for OCR completion per document:
# - When all non-blank pages have ocr_status=done:
#   - Enqueues document to structure-queue.fifo
#   - Sets documents.status=structuring (guarded latch)
# - Structure worker processes doc:
#   - Extracts entities (reg_no, name, dob, gender, etc.)
#   - Enqueues to match-queue.fifo
# - Match worker:
#   - Fuzzy searches extracted reg_no vs registry
#   - Sets match_status (matched|unmatched|manual_review)
#   - Enqueues to persist-queue.fifo
# - Persist worker:
#   - Embeds identity pages to Qdrant (384-dim vectors)
#   - Writes graph to Neo4j
#   - Sets documents.status=processed (final)

# Run once, or in loop: `while true; do make sweep; sleep 5; done`
```

### STEP 5: Start Stage Workers (in parallel terminals, optional)

If you want explicit control instead of one sweeper, run individual workers:

```bash
# Terminal A: Structure worker
make stage-worker STAGE=structure

# Terminal B: Match worker
make stage-worker STAGE=match

# Terminal C: Persist worker
make stage-worker STAGE=persist
```

Or let `make sweep` orchestrate all three (recommended for simplicity).

---

## Monitoring & Debugging

### Check Document Status

```bash
# Query Postgres directly
uv run python -c "
import asyncio
from shared.db import session_scope
from cloud.ingest.storage_db import DocumentRepository

async def check():
    async with session_scope() as session:
        docs = await DocumentRepository(session).list_all(limit=10)
        for doc in docs:
            print(f'{doc.document_id[:8]}: status={doc.status}')

asyncio.run(check())
"
```

### View Raw Data in MinIO

```bash
# Access MinIO UI
# http://localhost:9000
# Username: minioadmin
# Password: minioadmin
# Bucket: documents/
# Contents: <doc_id>/{ original.pdf, pages/page_NNN.png, manifest.json }
```

### Query Neo4j Graph

```bash
# Access Neo4j UI
# http://localhost:7687
# Username: neo4j
# Password: password
# Query examples:
MATCH (d:Document)-[:HAS_PAGE]->(p:Page) RETURN count(d), count(p)
MATCH (p:Person) WHERE p.registration_no IS NOT NULL RETURN p.registration_no, p.name LIMIT 5
```

### Query Qdrant Vectors

```bash
# Access Qdrant UI
# http://localhost:6333/dashboard
# Collection: document_pages
# Points: one per identity page per document (384-dim cosine)
```

---

## Complete Example: Run 3 PDFs

```bash
# Terminal 1: FastAPI server
make serve

# Terminal 2: Upload all 3 PDFs
make upload PDF_PATH="C:\Users\Wargstech\Desktop\wargstech\HomoeoFiles_local\AMR-MCH-26-A-07723.pdf" CATEGORY=practitioner TRIGGER=direct
make upload PDF_PATH="C:\Users\Wargstech\Desktop\wargstech\HomoeoFiles_local\AMR-MCH-26-A-22020.pdf" CATEGORY=practitioner TRIGGER=direct
make upload PDF_PATH="C:\Users\Wargstech\Desktop\wargstech\HomoeoFiles_local\AMR-MCH-26-A-22023.pdf" CATEGORY=practitioner TRIGGER=direct

# Terminal 3: OCR worker (drains ocr-queue)
make ocr-worker
# Wait until all pages are processed (watch logs for "done" messages)

# Terminal 4: Orchestration sweeper (fan-in: structure → match → persist)
make sweep

# Or run individual stage workers for more control:
# Terminal 4: Structure worker
make stage-worker STAGE=structure

# Terminal 5: Match worker
make stage-worker STAGE=match

# Terminal 6: Persist worker
make stage-worker STAGE=persist
```

### Expected Output

After all steps complete, you should have:

- **Postgres `documents`:** 3 rows with status=processed
- **Postgres `pages`:** ~52 total rows (all pages from 3 PDFs) with ocr_status=done (or failed/skipped)
- **Qdrant `document_pages`:** ~3-6 vectors (identity pages only: application_form, cover)
- **Neo4j:** 3 Document nodes, ~52 Page nodes, 1-3 Person nodes (matched practitioners)
- **MinIO `documents/`:** 3 subdirectories with original PDFs + PNG pages + manifests

---

## Troubleshooting

### "Tesseract not found"
- Ensure tesseract is on PATH: `tesseract --version`
- Install from https://github.com/UB-Mannheim/tesseract/wiki

### "OPENROUTER_API_KEY not set"
- Set in `.env`: `OPENROUTER_API_KEY=sk-or-...`
- Or export: `export OPENROUTER_API_KEY=sk-or-...`

### "ocr-worker stuck" / "No queues found"
- Verify `.env` SQS_* vars point to localhost:9324
- Check ElasticMQ is running: `docker ps | grep elasticmq`

### "Database connection refused"
- Ensure `make up` completed: `docker ps | grep postgres`
- Or restart: `make down && make up`

### Pages marked "failed" instead of "done"
- Check logs: `docker logs docpipe-postgres` or worker stderr
- Common: handwritten page with VLM unavailable (no OPENROUTER_API_KEY)
- Common: blank page (intentionally skipped, marked ocr_status=skipped)

---

## Next Steps After Running Locally

1. **Examine results** in Postgres/Neo4j/Qdrant UIs
2. **Optional:** Run evaluation dashboard (`make web-dev`) to inspect classifications, OCR, matches
3. **Deploy to AWS** (SQS/Lambda/Step Functions) — see `docs/` folder for infrastructure guidance

---

## Files & Make Targets Quick Reference

| Target | Purpose |
|--------|---------|
| `make up` | Start Docker containers |
| `make down` | Stop containers |
| `make init` | Initialize all DBs (idempotent) |
| `make serve` | FastAPI server (uvicorn :8000) |
| `make upload` | Render + upload PDF + manifest to S3/SQS |
| `make ocr-worker` | Drain ocr-queue, run OCR, enqueue structure |
| `make stage-worker STAGE=...` | Run single stage worker (structure\|match\|persist) |
| `make sweep` | Fan-in sweeper: trigger next stage when doc complete |
| `make test` | Run unit tests (fast, no Docker) |
| `make lint` | Ruff + mypy checks |
| `make format` | Auto-format with ruff |

