# Document Intelligence Pipeline

Scanned PDF → preprocessed images → OCR → structured entities → Qdrant + Neo4j + Postgres.

## Architecture

Two sides in one repo:

- **`nas/`** — runs on local NAS. Hashes PDF, rasterizes + preprocesses pages, uploads everything to S3, writes `manifest.json` **last** to trigger the cloud side.
- **`cloud/`** — triggered by S3 event when `manifest.json` lands. Runs ingest → OCR (Tesseract + LLM fallback) → entity extraction → persist (Qdrant / Neo4j / Postgres).
- **`shared/`** — code used on both sides (config, hashing, S3 client, logging, exceptions).

Design decisions and current build state live in `session_log.md` (project knowledge).

## Quickstart

```bash
# 1. Install Python deps (needs uv: https://github.com/astral-sh/uv)
make install

# 2. Copy env template
cp .env.example .env

# 3. Bring up local services (postgres, minio, qdrant, neo4j)
make up

# 4. Initialize each service (bucket, collection, constraints) — idempotent
make init

# 5. Verify
make test-integration
```

**For the full zero-to-100% walkthrough** (what each step does, per-service deep dive, troubleshooting, prod migration path), see [`docs/INTEGRATION.md`](docs/INTEGRATION.md).

## Local service URLs

| Service  | URL                       | Credentials                  |
|----------|---------------------------|------------------------------|
| Postgres | `localhost:5432`          | `pipeline` / `pipeline`      |
| MinIO    | http://localhost:9001     | `minioadmin` / `minioadmin`  |
| Qdrant   | http://localhost:6333     | —                            |
| Neo4j    | http://localhost:7474     | `neo4j` / `pipeline-dev`     |

## Layout

```
.
├── shared/        cross-side helpers (config, hashing, S3, logging, exceptions)
├── nas/           NAS-side: preprocess + uploader + manifest writer
├── cloud/         cloud-side: ingest, ocr, structure, persist
├── db/            SQL schema + future migrations
├── tests/
├── scripts/
├── docker-compose.yml
├── pyproject.toml
└── session_log.md (lives in project knowledge, not committed)
```
