# AWS Setup Guide — Document Intelligence Pipeline

> End-to-end runbook to deploy the pipeline to AWS. Datastores are **fully
> inside AWS**: Postgres on **RDS** (with **pgvector** as the vector store) and
> the graph on **Amazon Neptune** (openCypher). No external SaaS.
>
> Companion to the implementation plan
> `docs/superpowers/plans/2026-06-15-aws-orchestration.md` (the task-by-task
> build). This guide is the operator's checklist for a clean deploy + smoke test.

---

## 1. Architecture at a glance

```
NAS uploader ──put──> S3 bucket (documents/<id>/{original.pdf, pages/*.png, manifest.json})
                          │  manifest.json ObjectCreated
                          ▼
                  SQS ingest (standard)
                          ▼
                  λ ingest  ──per page──> SQS ocr (FIFO)
                          │                     ▼
                          │                 λ ocr  (Tesseract + VLM via OpenRouter)
                          │                     │ writes pages.ocr_status
                          ▼                     ▼
            EventBridge (rate 2m) ─────> λ sweeper  (fan-in: OCR-complete → SQS structure)
                                                ▼
                          SQS structure → λ structure → SQS match → λ match
                                                ▼                       ▼
                          SQS persist → λ persist → SQS index → λ index
                                          │                        │
                                          ▼                        ▼
                          RDS Postgres (relational + pgvector document_pages)
                          Amazon Neptune (Document/Page/Person graph, openCypher)

  All λ are container images in ECR, VPC-attached (private subnets).
  Outbound to OpenRouter via NAT. RDS + Neptune reachable only from the λ SG.
```

**Datastores (all in AWS):**
| Concern | Service | Notes |
|---|---|---|
| Relational | RDS PostgreSQL 16 | `documents`, `pages`, `reference_data`, dashboard, etc. |
| Vector | RDS pgvector | `document_pages(embedding vector(384))`, cosine `<=>`. Same instance as relational. |
| Graph | Amazon Neptune (Serverless) | openCypher; MERGE-on-natural-key. `GRAPH_BACKEND=neptune`. |
| Object | S3 | `documents/<id>/...`; manifest.json upload is the ingest trigger. |
| Queues | SQS | ingest=standard (S3 requires it); all stage queues FIFO. |
| Secrets | Secrets Manager | DB URL, OpenRouter key, session secret. |

**Why these choices** (see CLAUDE.md "Locked decisions"):
- **pgvector over Qdrant**: identity-page-only embeddings are tiny; co-locating
  vectors in the same Postgres removes a service *and* lets the persist stage
  write vectors inside its own transaction (no cross-store consistency gap).
- **Neptune over self-hosted Neo4j**: managed, openCypher-compatible so the
  `MERGE` writes port directly; Serverless keeps the dev baseline low. Neptune
  auto-indexes every property and **rejects `CREATE CONSTRAINT`/`CREATE INDEX`**
  — so `ensure_constraints()` is a no-op when `GRAPH_BACKEND=neptune`
  (uniqueness is enforced by our MERGE keys, not DB constraints).

---

## 2. Prerequisites

- **AWS account** with admin (or scoped infra) credentials; `aws configure` done.
- **Tools**: `terraform >= 1.7`, `docker`, `aws` CLI v2, `psql`, `uv`.
- **Region**: `ap-south-1` (default; matches `AWS_REGION`).
- **OpenRouter API key** — the sole cloud-OCR credential (handwriting VLM + LLM).
- A machine that can reach the VPC private subnets for the one-time DB seeding
  (VPN/bastion), or temporarily flip RDS `publicly_accessible` (revert after).

### 2.1 One-time Terraform state backend (manual)

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
aws s3api create-bucket --bucket "terraform-state-docintel-$ACCOUNT" \
  --region ap-south-1 --create-bucket-configuration LocationConstraint=ap-south-1
aws s3api put-bucket-versioning --bucket "terraform-state-docintel-$ACCOUNT" \
  --versioning-configuration Status=Enabled
aws dynamodb create-table --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST --region ap-south-1
```

Put the bucket name into `infra/providers.tf` `backend "s3" { bucket = ... }`.

---

## 3. Configure Terraform variables

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
```

Fill `terraform.tfvars` (NEVER commit it):

```hcl
aws_region         = "ap-south-1"
environment        = "dev"
db_password        = "<strong-random>"
openrouter_api_key = "sk-or-..."
session_secret     = "<>=32 random chars>"
s3_bucket_name     = "docintel-documents-dev"
ecr_image_tag      = "latest"
alarm_email        = "ops@your-domain.com"
```

> There are **no** Qdrant/Neo4j SaaS variables — both stores are provisioned
> in-account (RDS pgvector + Neptune).

---

## 4. Build & push Lambda images

All stages ship as container images (`public.ecr.aws/lambda/python:3.12` base).
ECR repos are created by Terraform, so apply the ECR + (optionally everything)
first, *then* push images, *then* the Lambda functions resolve their `image_uri`.

Two-phase apply avoids the chicken-and-egg (Lambda needs an image to exist):

```bash
cd infra
terraform init
# Phase 1: create ECR repos (and the rest of the non-Lambda infra)
terraform apply -target=aws_ecr_repository.ingest \
                -target=aws_ecr_repository.ocr \
                -target=aws_ecr_repository.light \
                -target=aws_ecr_repository.persist_index

# Build + push all four images
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=ap-south-1 ENVIRONMENT=dev
cd ..
./infra/docker/build_push.sh latest
```

Image variants:
| Image | Stages | Heavy deps |
|---|---|---|
| `ingest` | ingest | PyMuPDF |
| `ocr` | ocr | Tesseract (`eng`+`mar`+`hin`) + OpenCV + pyzbar + openai SDK |
| `light` | structure, match, sweeper | none |
| `persist-index` | persist, index | sentence-transformers + torch-cpu (MiniLM baked in) |

> The persist/index image **bakes the embedding model at build time**
> (`paraphrase-multilingual-MiniLM-L12-v2`, ~400 MB) so there's no cold-start
> download. It no longer bundles a Qdrant client — vectors go to RDS pgvector
> via asyncpg, and the graph to Neptune via the `neo4j` Bolt driver.

---

## 5. Full apply

```bash
cd infra
terraform plan -var-file=terraform.tfvars -out=tfplan
terraform apply tfplan
```

Note the outputs:
```
rds_endpoint            = docintel-dev.xxxx.ap-south-1.rds.amazonaws.com:5432
neptune_endpoint        = docintel-dev.cluster-xxxx.ap-south-1.neptune.amazonaws.com:8182
sqs_ingest_queue_url    = https://sqs.../docintel-dev-ingest
sqs_ocr_queue_url       = https://sqs.../docintel-dev-ocr.fifo
...
```

Verify the 7 Lambdas are Active:
```bash
aws lambda list-functions \
  --query "Functions[?starts_with(FunctionName,'docintel-dev')].[FunctionName,State]" \
  --output table
```

---

## 6. One-time data plane init

Run from a host that can reach the RDS + Neptune endpoints (bastion/VPN, or
temporarily set RDS `publicly_accessible=true`, apply, seed, then revert).

```bash
RDS=<rds_endpoint without :5432>
export DATABASE_URL="postgresql+asyncpg://pipeline:<DB_PASSWORD>@$RDS/doc_pipeline"

# 6.1 Relational schema (creates all tables AND the pgvector document_pages table)
psql "postgresql://pipeline:<DB_PASSWORD>@$RDS:5432/doc_pipeline" -f db/schema.sql

# 6.2 (If the DB predates pgvector) enable extension + table idempotently
uv run python -m scripts.apply_pgvector

# 6.3 Reference registry (~92K rows) + dashboard user + cost table
uv run python -m scripts.load_reference_data
uv run python -m scripts.apply_cost_events
uv run python -m scripts.add_dashboard_user
```

> `db/schema.sql` includes `CREATE EXTENSION IF NOT EXISTS vector;`. On RDS the
> `vector` extension is available on PostgreSQL 16 — `CREATE EXTENSION` succeeds
> as the `pipeline` master user (it has `rds_superuser`).

### 6.4 Graph (Neptune)

Neptune needs **no schema/constraints** — it auto-indexes and rejects DDL, and
the app skips `ensure_constraints()` when `GRAPH_BACKEND=neptune`. Just verify
connectivity from inside the VPC:

```bash
# openCypher over HTTPS
curl -sk https://<neptune_endpoint>/opencypher \
  -d "query=MATCH (n) RETURN count(n) AS n"
```

The Lambdas connect with the `neo4j` Bolt driver to
`neo4j+s://<neptune_endpoint>:8182` (TLS required). For dev, **IAM auth is
disabled** on the cluster, so `NEO4J_USER`/`NEO4J_PASSWORD` are unused; the
security group (λ SG → Neptune :8182) is the access boundary. To turn IAM auth
on later, set the cluster's `iam_database_authentication_enabled=true` and have
the persist/index Lambdas generate a SigV4 auth token.

---

## 7. Smoke test (one bundle)

Point a local `.env` at real AWS (blank the local endpoints):

```bash
S3_ENDPOINT_URL=
SQS_ENDPOINT_URL=
AWS_ACCESS_KEY_ID=...        # an IAM user/role that can PutObject to the bucket
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=docintel-documents-dev
DATABASE_URL=postgresql+asyncpg://pipeline:<DB_PASSWORD>@<RDS>/doc_pipeline
GRAPH_BACKEND=neptune
NEO4J_URI=neo4j+s://<neptune_endpoint>:8182
SQS_OCR_QUEUE_URL=<terraform output>
SQS_STRUCTURE_QUEUE_URL=<...>
SQS_MATCH_QUEUE_URL=<...>
SQS_PERSIST_QUEUE_URL=<...>
SQS_INDEX_QUEUE_URL=<...>
OPENROUTER_API_KEY=sk-or-...
```

Upload a bundle (NAS uploader → real S3):
```bash
uv run python -m scripts.upload_pdf HomoeoFiles_local/AMR-MCH-26-A-07723.pdf \
  --trigger direct --category practitioner
```

Watch the chain:
```bash
aws logs tail /aws/lambda/docintel-dev-ingest   --since 5m --follow   # ingest_lambda.done
aws logs tail /aws/lambda/docintel-dev-ocr      --since 5m --follow   # ocr.done x N
aws logs tail /aws/lambda/docintel-dev-sweeper  --since 5m            # sweep_done advanced=1
for s in structure match persist index; do
  echo "== $s =="; aws logs tail /aws/lambda/docintel-dev-$s --since 10m
done
```

Verify all stores:
```sql
-- RDS relational + pgvector
SELECT status, match_status FROM documents WHERE document_id='<id>';      -- processed
SELECT count(*) FROM document_pages WHERE document_id='<id>';             -- >= 1 (identity pages)
```
```bash
# Neptune graph (from in-VPC)
curl -sk https://<neptune_endpoint>/opencypher \
  -d "query=MATCH (d:Document {document_id:'<id>'})-[:HAS_PAGE]->(p:Page) RETURN d.document_id, count(p)"
# S3 objects
aws s3 ls s3://docintel-documents-dev/documents/<id>/ --recursive | wc -l   # original + pages + manifest
```

---

## 8. Operations

- **DLQs**: any message in `docintel-dev-<stage>-dlq[.fifo]` = a unit failed 3
  retries. CloudWatch alarm → SNS email (`alarm_email`). Inspect, fix, redrive.
- **Costs**: `cost_events` table + `/observability` dashboard track paid LLM/VLM
  spend. Neptune Serverless + RDS are the fixed-baseline costs; NAT gateways too.
- **Scaling**: for 200+ docs, do **not** use the in-process folder runner — use
  the NAS uploader batch loop → S3 → SQS fan-out (see CLAUDE.md "Active threads"
  / `scripts/batch_upload.py` once built).

---

## 9. Teardown

```bash
cd infra
terraform destroy -var-file=terraform.tfvars
```

Before prod: set RDS `deletion_protection=true`, `skip_final_snapshot=false`,
Multi-AZ; enable Neptune IAM auth; tighten the Lambda egress SG.

---

## 10. Cost notes (dev, ap-south-1, rough)

| Resource | ~Monthly |
|---|---|
| RDS db.t3.micro (incl. pgvector — no extra) | ~$15 |
| Neptune Serverless (min NCU, idle-heavy) | ~$ scales with NCU-hours |
| 2× NAT gateway | ~$65 (largest fixed cost — collapse to 1 AZ for dev to halve) |
| SQS / Lambda / S3 / ECR | usage-based, low at dev scale |

> Biggest dev-cost lever: drop to a **single NAT gateway** (one AZ) — Lambdas
> still reach OpenRouter; you lose NAT HA, which is fine for dev.
