# DocIntel AWS Infrastructure — Zero Docker, Full Managed Services

> **Status:** Phase 0 — Foundation deployed. This README documents the infrastructure and how to use it.
>
> **Architecture:** AWS SAM (Serverless Application Model) → CloudFormation → S3, SQS, RDS, ElastiCache, Lambda, ECS Fargate, CloudWatch, Secrets Manager, KMS, ALB, IAM.
>
> **Region:** `ap-south-1` (Mumbai) — lowest latency for India.
>
> **Cost:** ~$89/month base + ~$6 per 200-document batch.
>
> **Deploy time:** 8–15 minutes for initial stack creation.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [One-Command Deploy](#2-one-command-deploy)
3. [One-Command Destroy](#3-one-command-destroy)
4. [Infrastructure Components](#4-infrastructure-components)
5. [How the Pipeline Works](#5-how-the-pipeline-works)
6. [Monitoring & Debugging](#6-monitoring--debugging)
7. [Cost Breakdown](#7-cost-breakdown)
8. [Security](#8-security)
9. [Troubleshooting](#9-troubleshooting)
10. [Next Steps (Phase 1)](#10-next-steps-phase-1)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              AWS CLOUD                                   │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  FRONTEND: Vercel (Next.js app)                                   │  │
│  │  • Edge CDN, auto-deploy from GitHub push                        │  │
│  │  • Zero server management                                         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  API: ECS Fargate (FastAPI + WebSocket)                           │  │
│  │  • Always-on for real-time dashboard updates                       │  │
│  │  • Auto-scaling: 1–4 tasks based on CPU/memory                   │  │
│  │  • 70% cost savings via FARGATE_SPOT weighting                   │  │
│  │  • Health checks, rolling deployments, zero-downtime updates       │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  STAGE WORKERS: Lambda (serverless, auto-scaling)                │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │  │
│  │  │ OCR    │ │Struct. │ │ Match  │ │Persist │ │ Index  │       │  │
│  │  │(Tess.) │ │        │ │        │ │        │ │        │       │  │
│  │  │1024MB │ │ 512MB  │ │ 256MB  │ │ 512MB  │ │ 512MB  │       │  │
│  │  │ 60s   │ │  30s   │ │  15s   │ │  30s   │ │  30s   │       │  │
│  │  │1000conc│ │  50conc│ │  50conc│ │  50conc│ │  50conc│       │  │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘       │  │
│  │  ┌────────┐                                                        │  │
│  │  │ VLM    │  ← Invoked by OCR Lambda (not SQS)                  │  │
│  │  │(OpenR.)│  • 2048 MB, 120s timeout, 50 concurrent               │  │
│  │  └────────┘                                                        │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  MESSAGE QUEUE: SQS (FIFO)                                         │  │
│  │  • ocr-queue.fifo       (page-level, 10 msg batch)               │  │
│  │  • structure-queue.fifo (document-level, 5 msg batch)            │  │
│  │  • match-queue.fifo     (document-level, 5 msg batch)          │  │
│  │  • persist-queue.fifo   (document-level, 5 msg batch)          │  │
│  │  • index-queue.fifo     (document-level, 5 msg batch)          │  │
│  │  • Dead-letter queues for each (max 3 retries, 14-day retention) │  │
│  │  • Auto-scaling: Lambda pulls from queue automatically           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  DATABASE: RDS PostgreSQL 16 (managed)                             │  │
│  │  • db.t3.medium (2 vCPU, 4 GB, 20 GB storage)                    │  │
│  │  • Auto-scaling storage up to 100 GB                             │  │
│  │  • Daily backups, 7-day retention, point-in-time recovery        │  │
│  │  • Performance Insights, CloudWatch logs export                  │  │
│  │  • Multi-AZ option (adds ~$45/month for HA)                      │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  CACHE: ElastiCache Redis (managed)                                │  │
│  │  • cache.t3.micro (1 node, 0.5 GB)                                 │  │
│  │  • Real-time event pub/sub (WebSocket → Redis → client)          │  │
│  │  • Search suggestion indexes (name, reg_no)                      │  │
│  │  • Session store (if needed)                                       │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  OBJECT STORAGE: S3 (managed)                                      │  │
│  │  • 99.999999999% durability (11 nines)                            │  │
│  │  • Versioning enabled (accidental deletion protection)           │  │
│  │  • Lifecycle: Standard-IA after 30 days, Glacier after 365 days  │  │
│  │  • Cross-region replication option (for DR)                        │  │
│  │  • Enforced HTTPS (TLS)                                          │  │
│  │  • Event notification: manifest.json → SQS ocr-queue            │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  VECTOR DB: Qdrant Cloud (managed, free tier)                      │  │
│  │  • 1M vectors (384-dim cosine) — more than enough for 92K docs     │  │
│  │  • No cluster management, API-only access                          │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  GRAPH DB: Neo4j Aura (managed, free tier)                        │  │
│  │  • 200K nodes / 400K relationships — sufficient for 92K practitioners│  │
│  │  • No cluster management, API-only access                           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  MONITORING: CloudWatch (managed)                                  │  │
│  │  • Dashboard: Pipeline health, queue depth, Lambda invocations     │  │
│  │  • Alarms: Queue depth > 100, Lambda errors > 5%, RDS CPU > 80%  │  │
│  │  • SNS topic for alert notifications (email/SMS/Slack)            │  │
│  │  • X-Ray distributed tracing across Lambda → SQS → Lambda chains  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  SECURITY: Secrets Manager + KMS + IAM (managed)                   │  │
│  │  • All credentials in one Secrets Manager secret (auto-rotation) │  │
│  │  • KMS encryption key (auto-rotation every 90 days)              │  │
│  │  • IAM roles with least privilege (no hardcoded credentials)     │  │
│  │  • No secrets in environment variables or code                    │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  NETWORK: VPC + ALB + Security Groups (managed)                    │  │
│  │  • RDS and ElastiCache in private subnets (no public access)     │  │
│  │  • ALB in public subnets (HTTP, upgrade to HTTPS in Phase 2)   │  │
│  │  • Security groups: least privilege, no 0.0.0.0/0 except ALB   │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. One-Command Deploy

### Prerequisites

1. **AWS CLI** installed and configured:
   ```bash
   aws configure
   # Enter your AWS Access Key ID, Secret Key, region (ap-south-1), output format (json)
   ```

2. **SAM CLI** installed:
   ```bash
   pip install aws-sam-cli
   ```

3. **Docker** installed (for building Lambda layers if needed):
   ```bash
   docker --version
   ```

4. **VPC with subnets** in your AWS account (ap-south-1):
   - 2 public subnets (for ALB)
   - 2 private subnets (for RDS, ElastiCache, ECS)
   - If you don't have a VPC, use the default VPC or create one via AWS Console.

### Deploy

```bash
# Interactive deploy (recommended for first time)
make aws-deploy

# Or run the script directly
python cloud/infrastructure/scripts/deploy.py --env production --region ap-south-1
```

**What the script does:**
1. Validates AWS credentials and SAM CLI
2. Prompts for VPC and subnet IDs (or auto-detects default VPC)
3. Prompts for external service credentials (Qdrant Cloud, Neo4j Aura, OpenRouter)
4. Prompts for optional overrides (RDS instance class, storage, etc.)
5. Runs `sam deploy` to create the CloudFormation stack
6. Outputs all endpoints, queue URLs, and credentials locations
7. Saves outputs to `docintel-production-outputs.json`

**Deploy time:** 8–15 minutes (RDS is the slowest component, ~10 min).

**After deploy:**
- Seed the RDS database with `db/schema.sql` and `scripts/load_reference_data.py`
- Build and push the FastAPI Docker image to ECR (Phase 2)
- Deploy the Next.js app to Vercel (Phase 2)

---

## 3. One-Command Destroy

```bash
# WITH confirmation (recommended)
make aws-destroy

# Or run the script directly
python cloud/infrastructure/scripts/destroy.py --env production --region ap-south-1

# WITHOUT confirmation (DANGEROUS — use only for automated teardown)
make aws-destroy-force
```

**What gets destroyed:**
- All S3 documents and versions
- All RDS data (including reference_data)
- All SQS messages and queues
- All ElastiCache data
- All Lambda functions and logs
- All ECS services and tasks
- All CloudWatch dashboards and alarms
- All Secrets (KMS key is scheduled for deletion, not immediate)

**Destroy time:** 5–10 minutes.

---

## 4. Infrastructure Components

### S3 Bucket (`docintel-documents-{account}-{env}`)

```
s3://docintel-documents-123456789012-production/
├── documents/
│   ├── {doc_id}/
│   │   ├── original.pdf          ← uploaded first
│   │   ├── pages/
│   │   │   ├── page_001.png      ← uploaded second
│   │   │   ├── page_002.png
│   │   │   └── ...
│   │   └── manifest.json         ← uploaded LAST (triggers S3 event → SQS → Lambda)
│   └── ...
```

**Lifecycle:**
- Standard storage: 0–30 days
- Standard-IA: 30–365 days (~40% cheaper)
- Glacier: 365+ days (~80% cheaper)

**Security:**
- Versioning enabled (accidental deletion protection)
- Enforced HTTPS (no HTTP access)
- Block all public access

### SQS Queues (FIFO)

| Queue | Type | Batch Size | Visibility | Dead Letter | Purpose |
|---|---|---|---|---|---|
| ocr-queue.fifo | page-level | 10 | 120s | 3 retries | Tesseract OCR + VLM fallback |
| structure-queue.fifo | document-level | 5 | 120s | 3 retries | Entity extraction (regex + LLM) |
| match-queue.fifo | document-level | 5 | 120s | 3 retries | Fuzzy match vs reference_data |
| persist-queue.fifo | document-level | 5 | 120s | 3 retries | Embed to Qdrant + graph to Neo4j |
| index-queue.fifo | document-level | 5 | 120s | 3 retries | Summarize + keywords + entities |

**FIFO (First-In-First-Out):** Ensures messages are processed in order. Required for per-document stage ordering.

**Content-based deduplication:** Prevents duplicate messages for the same page/document.

### RDS PostgreSQL 16

| Setting | Value | Notes |
|---|---|---|
| Instance | db.t3.medium | 2 vCPU, 4 GB RAM. Scale to db.t3.large for higher load. |
| Storage | 20 GB (gp3) | Auto-scales to 100 GB |
| Engine | PostgreSQL 16.3 | Latest stable |
| Multi-AZ | false | Set to true for production HA (+~$45/month) |
| Backups | 7 days | Daily automated backups, point-in-time recovery |
| Encryption | AES-256 | At-rest encryption via KMS |
| Public access | false | Private subnet only |

**Connection:**
```bash
# From a bastion host or AWS Systems Manager Session Manager
psql -h {RDS_ENDPOINT} -U pipeline -d doc_pipeline
# Password: from Secrets Manager → docintel/production/credentials → RDS_PASSWORD
```

### ElastiCache Redis

| Setting | Value | Notes |
|---|---|---|
| Node type | cache.t3.micro | 1 node, 0.5 GB. Free tier eligible. |
| Engine | Redis 7.1 | Latest stable |
| Multi-AZ | false | Single node for cost savings |

**Usage:**
- Real-time event pub/sub (WebSocket → Redis → dashboard client)
- Search suggestion cache (name, reg_no indexes)
- Session store (if needed)
- Rate limiting counters

### Lambda Functions

| Function | Memory | Timeout | Concurrency | Trigger | Cost per 1M invocations |
|---|---|---|---|---|---|
| docintel-ocr | 1024 MB | 60s | 100 | SQS ocr-queue | ~$166 |
| docintel-vlm | 2048 MB | 120s | 50 | Lambda invoke (by OCR) | ~$333 |
| docintel-structure | 512 MB | 30s | 50 | SQS structure-queue | ~$83 |
| docintel-match | 256 MB | 15s | 50 | SQS match-queue | ~$41 |
| docintel-persist | 512 MB | 30s | 50 | SQS persist-queue | ~$83 |
| docintel-index | 512 MB | 30s | 50 | SQS index-queue | ~$83 |

**Cold start:** Python 3.12 Lambda has ~500ms cold start. For OCR (Tesseract), expect ~3-5s cold start due to binary initialization. Provisioned concurrency (Phase 4) can eliminate this.

### ECS Fargate API

| Setting | Value | Notes |
|---|---|---|
| CPU | 512 (0.5 vCPU) | 256–2048 available |
| Memory | 1024 MB | 512–4096 available |
| Tasks | 1 | Auto-scales to 4 based on CPU/memory |
| Capacity | FARGATE_SPOT (70%) + FARGATE (30%) | Spot saves ~70% cost, FARGATE is fallback |
| Health check | /health | Every 30s, 3 retries |

**The API server is always-on** for:
- WebSocket real-time updates to dashboard
- Aether chat interface (instant response)
- Engine Room control panel (instant response)
- Static file serving (document images via S3 proxy)

---

## 5. How the Pipeline Works

### Step-by-Step Flow

```
1. NAS Machine (Your Local Computer)
   PDF arrives → python nas/upload_agent.py my-bundle.pdf
   ├── PyMuPDF renders pages to PNG (300 DPI)
   ├── OpenCV preprocesses (grayscale, denoise, deskew, threshold)
   ├── Tesseract triage classifies page_type and content_type
   ├── boto3 uploads to S3:
   │   s3://docintel-documents/documents/{doc_id}/original.pdf  (first)
   │   s3://docintel-documents/documents/{doc_id}/pages/page_001.png  (second)
   │   ...
   │   s3://docintel-documents/documents/{doc_id}/manifest.json  (LAST)
   │       ↑ This upload triggers the S3 event notification
   │
   └── S3 ObjectCreated:Put on manifest.json
       ↓
       S3 Event Notification → SQS ocr-queue.fifo
       Message: {document_id, s3_prefix, page_count, category, pages: [...]}

2. Lambda: OCR (Auto-Scaled, 100 Concurrent)
   Polls SQS ocr-queue.fifo → receives 1-10 page messages
   For each page:
   ├── Download page image from S3
   ├── Tesseract OCR (eng+mar+hin) → per-word confidence + bbox
   ├── If confidence < 70 OR handwritten → invoke VLM Lambda
   │   VLM Lambda: OpenRouter → Gemini 2.5 Flash → transcription
   │   VLM returns text + confidence (fixed 85.0)
   ├── Write OCR result to RDS (pages table: raw_text, confidence, ocr_status)
   └── If last page of document → send to SQS structure-queue.fifo
       Message: {document_id}

3. Lambda: Structure (Auto-Scaled, 50 Concurrent)
   Polls SQS structure-queue.fifo → receives 1-5 document messages
   For each document:
   ├── Read all pages from RDS
   ├── Regex pre-pass (registration_no, dates, phone, email, pincode)
   ├── LLM pass (OpenRouter, text-only) for identity pages only
   │   → refined page_type, NER (names, addresses, orgs)
   ├── Roll up best identity across pages (name, reg_no, DOB, gender)
   ├── Write to RDS (documents table: structured entities)
   └── Send to SQS match-queue.fifo
       Message: {document_id}

4. Lambda: Match (Auto-Scaled, 50 Concurrent)
   Polls SQS match-queue.fifo → receives 1-5 document messages
   For each document:
   ├── Exact registration_no lookup in RDS reference_data
   ├── Name cross-check (rapidfuzz token_sort_ratio)
   ├── DOB cross-check (±1 day tolerance)
   ├── Decision:
   │   ├── Exact reg_no + name ≥ 90% + DOB match → matched
   │   ├── Exact reg_no + name 65-89% + DOB match → manual_review
   │   ├── No reg_no OR name < 60% → unmatched
   │   └── Non-practitioner → not_applicable
   ├── Write match_status to RDS (documents table)
   └── Send to SQS persist-queue.fifo
       Message: {document_id}

5. Lambda: Persist (Auto-Scaled, 50 Concurrent)
   Polls SQS persist-queue.fifo → receives 1-5 document messages
   For each document:
   ├── Read identity pages from RDS
   ├── Generate 384-dim embedding (paraphrase-multilingual-MiniLM-L12-v2)
   ├── Upsert to Qdrant Cloud (document_pages collection)
   ├── Write graph to Neo4j Aura:
   │   MERGE (Document)-[:HAS_PAGE]->(Page)
   │   MERGE (Person)-[:BELONGS_TO]->(Document)
   │   MERGE (Page)-[:MENTIONS]->(Entity)
   ├── Update RDS documents.status = 'processed'
   └── Send to SQS index-queue.fifo
       Message: {document_id}

6. Lambda: Index (Auto-Scaled, 50 Concurrent)
   Polls SQS index-queue.fifo → receives 1-5 document messages
   For each document:
   ├── Generate document summary (from structured data, not LLM)
   ├── Extract keywords (TF-IDF or LLM, mode-selectable)
   ├── Extract 6-type entities (practitioner/organization/vendor/government_body/educational_institute/hospital)
   ├── Write to RDS: documents.document_summary, pages.search_keywords, pages.index_entities
   ├── Update RDS documents.index_status = 'done'
   └── Done. No further queue.

7. ECS Fargate API (Always-On)
   ├── WebSocket connections to dashboard clients
   ├── Real-time updates: RDS trigger → Redis pub/sub → WebSocket push
   ├── Aether chat: natural language query → regex parse → retrieval cascade
   └── Engine Room: pipeline control, stage inspector, parameter tuner
```

### Timing Estimates (200 documents, 13 pages each = 2600 pages)

| Stage | Parallelism | Per-Unit Time | Total Time |
|---|---|---|---|
| Upload (NAS) | 4 workers | ~30s/doc | ~25 min |
| OCR (Tesseract) | 100 concurrent Lambda | ~2s/page | ~52 min |
| OCR (VLM fallback, ~20% of pages) | 50 concurrent Lambda | ~5s/page | ~17 min |
| Structure | 50 concurrent Lambda | ~3s/doc | ~12 min |
| Match | 50 concurrent Lambda | ~2s/doc | ~8 min |
| Persist | 50 concurrent Lambda | ~3s/doc | ~12 min |
| Index | 50 concurrent Lambda | ~3s/doc | ~12 min |
| **Total pipeline** | | | **~60–90 min** (overlapping stages) |

---

## 6. Monitoring & Debugging

### CloudWatch Dashboard

URL: (from stack outputs) → `DashboardUrl`

**Dashboard widgets:**
- OCR Lambda invocations (per minute)
- VLM Lambda invocations (per minute)
- SQS queue depths (all 5 queues, stacked)
- Lambda error rates (all 6 functions, stacked)
- RDS CPU utilization (%)
- ECS API task count (running tasks)
- ALB request count (requests per minute)
- ALB 5xx error rate (errors per minute)

### CloudWatch Alarms

| Alarm | Trigger | Action |
|---|---|---|
| OCR Queue Depth > 100 | 10 minutes | SNS alert → email/SMS |
| Lambda Error Rate > 5% | 5 minutes | SNS alert → email/SMS |
| RDS CPU > 80% | 5 minutes | SNS alert → email/SMS |
| ALB 5xx Errors > 10 | 5 minutes | SNS alert → email/SMS |

### CloudWatch Logs

```bash
# API ECS logs
make aws-logs

# Lambda logs
make aws-logs-ocr       # OCR Lambda
make aws-logs-vlm       # VLM Lambda
make aws-logs-structure # Structure Lambda
make aws-logs-match     # Match Lambda
make aws-logs-persist   # Persist Lambda
make aws-logs-index     # Index Lambda

# Or directly with AWS CLI
aws logs tail /aws/lambda/docintel-production-ocr --follow
aws logs tail /aws/ecs/docintel-production-api --follow
```

### SQS Queue Status

```bash
make aws-sqs-status

# Or directly
aws sqs get-queue-attributes --queue-url <queue-url> --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
```

### CloudWatch Metrics

```bash
# Lambda invocations in the last hour
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=docintel-production-ocr \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Sum
```

---

## 7. Cost Breakdown

### Base Monthly Cost (Idle — No Processing)

| Service | Spec | Monthly (USD) | Monthly (INR, ~₹83) |
|---|---|---|---|
| RDS PostgreSQL | db.t3.medium | ~$45 | ~₹3,735 |
| ElastiCache Redis | cache.t3.micro | ~$12 | ~₹996 |
| ECS Fargate API | 0.5 vCPU, 1 GB (1 task, Spot) | ~$15 | ~₹1,245 |
| S3 Storage | 100 GB | ~$2.30 | ~₹191 |
| Vercel (Pro) | Next.js app | ~$15 | ~₹1,245 |
| Qdrant Cloud | Free tier (1M vectors) | $0 | ₹0 |
| Neo4j Aura | Free tier (200K nodes) | $0 | ₹0 |
| Lambda (idle) | $0 when not invoked | $0 | ₹0 |
| SQS (idle) | $0 when no messages | $0 | ₹0 |
| CloudWatch | Dashboard + alarms (basic) | ~$3 | ~₹249 |
| **Total Base** | | **~$92** | **~₹7,636** |

### Processing Cost (Per 200-Document Batch)

| Service | Per 200 Docs | Cost (USD) | Cost (INR) |
|---|---|---|---|
| SQS Messages | ~2600 messages | ~$0.001 | ~₹0.08 |
| Lambda OCR (Tesseract) | ~2600 invocations × 10s × 1024 MB | ~$0.43 | ~₹36 |
| Lambda VLM | ~400 invocations × 30s × 2048 MB | ~$0.41 | ~₹34 |
| Lambda Structure | ~200 invocations × 5s × 512 MB | ~$0.03 | ~₹2.50 |
| Lambda Match | ~200 invocations × 3s × 256 MB | ~$0.01 | ~₹0.80 |
| Lambda Persist | ~200 invocations × 5s × 512 MB | ~$0.03 | ~₹2.50 |
| Lambda Index | ~200 invocations × 5s × 512 MB | ~$0.03 | ~₹2.50 |
| OpenRouter API | ~400 VLM calls | ~$5.00 | ~₹415 |
| S3 Requests | ~5000 GET/PUT | ~$0.02 | ~₹1.70 |
| RDS I/O | ~10K queries | ~$0 (included) | ₹0 |
| **Total Per Batch** | | **~$6.00** | **~₹498** |

### Total Monthly Scenarios

| Volume | Base + Processing | USD | INR |
|---|---|---|---|
| 200 docs / month | $92 + $6 | $98 | ~₹8,134 |
| 2,000 docs / month | $92 + $60 | $152 | ~₹12,616 |
| 20,000 docs / month | $92 + $600 | $692 | ~₹57,436 |

**Note:** At 20,000 docs/month, consider moving OCR workers to ECS Fargate (dedicated tasks, no Lambda cold starts, lower per-1000 cost at high volume). This is a Phase 4 optimization.

---

## 8. Security

### Credentials

- **No hardcoded credentials** in code, environment variables, or Git
- All credentials stored in **AWS Secrets Manager** (`docintel/production/credentials`)
- Secrets encrypted with **AWS KMS** (auto-rotates every 90 days)
- RDS password auto-generated by CloudFormation and stored in Secrets Manager
- Lambda and ECS access secrets via IAM role (no access keys needed)

### IAM Roles

| Role | Purpose | Permissions |
|---|---|---|
| LambdaExecutionRole | Lambda functions | S3 read/write, SQS send/receive/delete, Secrets read, CloudWatch logs, X-Ray, RDS describe, ElastiCache describe |
| EcsExecutionRole | ECS task execution | ECR pull, Secrets read, CloudWatch logs |
| EcsTaskRole | ECS task runtime | S3 read/write, SQS send/receive/delete, Secrets read, CloudWatch logs, X-Ray |

**Principle of least privilege:** Each role has only the permissions it needs. No wildcard `*:*` permissions.

### Network

- **RDS and ElastiCache** in private subnets (no public IP, no internet access)
- **ECS tasks** in private subnets (outbound internet via NAT, no inbound except ALB)
- **ALB** in public subnets (HTTP on port 80, HTTPS upgrade in Phase 2)
- **Security groups** are tight: RDS only allows 5432 from Lambda/ECS security groups; Redis only allows 6379 from Lambda/ECS security groups; ALB only allows 80/443 from configurable CIDR (default 0.0.0.0/0, restrict to your office IP in production)

### Data Protection

- **S3:** AES-256 encryption at rest, HTTPS enforcement, versioning, cross-region replication (optional)
- **RDS:** AES-256 encryption at rest, automated backups, point-in-time recovery, deletion protection (production only)
- **SQS:** KMS encryption for message bodies
- **Lambda:** No persistent storage (ephemeral /tmp only, cleared after invocation)

---

## 9. Troubleshooting

### Deployment Fails

**Symptom:** `sam deploy` fails with `CREATE_FAILED`.

**Common causes:**
1. **S3 bucket name already exists:** S3 bucket names are globally unique. If `docintel-documents-{account}-{env}` is taken, specify a custom name via `--parameter-overrides S3BucketName=your-unique-name`.
2. **VPC/Subnet IDs invalid:** Ensure the VPC and subnet IDs exist in the target region (ap-south-1). Subnets must be in different Availability Zones.
3. **RDS instance class not available:** `db.t3.medium` may not be available in all AZs. Try `db.t3.small` or `db.t3.large`.
4. **IAM permissions insufficient:** The AWS user needs `CloudFormation:*`, `IAM:*`, `S3:*`, `SQS:*`, `RDS:*`, `ElastiCache:*`, `Lambda:*`, `ECS:*`, `ALB:*`, `SecretsManager:*`, `KMS:*`, `CloudWatch:*`, `SNS:*`, `EC2:*` (VPC-related).

**Fix:** Check the CloudFormation events in AWS Console → CloudFormation → Stacks → docintel-production → Events. Find the first `CREATE_FAILED` event and fix the issue.

```bash
aws cloudformation describe-stack-events --stack-name docintel-production --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`].[LogicalResourceId,ResourceStatusReason]'
```

### Lambda Errors

**Symptom:** CloudWatch logs show `ERROR` in Lambda function.

**Common causes:**
1. **RDS connection timeout:** Lambda is in a VPC but the security group doesn't allow outbound to RDS. Check the `LambdaSecurityGroup` egress rules.
2. **S3 access denied:** The IAM role doesn't have S3 permissions. Check the `LambdaExecutionRole` policy.
3. **Secrets Manager access denied:** The IAM role doesn't have `secretsmanager:GetSecretValue`. Check the `LambdaExecutionRole` policy.
4. **Memory/timeout exceeded:** The Lambda function ran out of memory or hit the timeout. Check the function metrics in CloudWatch.

**Fix:**
```bash
# Check Lambda errors
aws logs tail /aws/lambda/docintel-production-ocr --follow

# Check Lambda metrics
aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Errors \
  --dimensions Name=FunctionName,Value=docintel-production-ocr \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) --period 60 --statistics Sum
```

### SQS Messages Stuck

**Symptom:** Queue depth is high and not decreasing.

**Common causes:**
1. **Lambda not triggered:** The SQS event mapping may not be connected. Check AWS Console → Lambda → docintel-production-ocr → Triggers → SQS.
2. **Lambda errors:** Messages are failing and being retried. Check the dead-letter queue depth.
3. **Lambda concurrency limit:** Reserved concurrency may be set too low. Check the `ReservedConcurrentExecutions` setting.

**Fix:**
```bash
# Check queue depth
make aws-sqs-status

# Check dead-letter queue depth
aws sqs get-queue-attributes --queue-url <dlq-url> --attribute-names ApproximateNumberOfMessages

# Check Lambda triggers
aws lambda list-event-source-mappings --function-name docintel-production-ocr
```

### RDS Connection Issues

**Symptom:** Lambda can't connect to RDS.

**Common causes:**
1. **RDS is still creating:** RDS takes ~10 minutes to create. Wait until the CloudFormation stack shows `CREATE_COMPLETE`.
2. **Security group rules:** The `RdsSecurityGroup` must allow 5432 from the `LambdaSecurityGroup` and `EcsSecurityGroup`.
3. **VPC routing:** Lambda is in the VPC but the subnets don't have a route to the RDS subnet. Ensure all subnets are in the same VPC.

**Fix:**
```bash
# Check RDS status
aws rds describe-db-instances --db-instance-identifier docintel-production-postgres --query 'DBInstances[0].DBInstanceStatus'

# Check security group rules
aws ec2 describe-security-groups --group-ids <rds-security-group-id> --query 'SecurityGroups[0].IpPermissions'
```

### ECS API Not Responding

**Symptom:** ALB returns 502 Bad Gateway or 503 Service Unavailable.

**Common causes:**
1. **ECS task not running:** The task may be failing health checks. Check ECS service events.
2. **Docker image not found:** The ECR repository may not have the `docintel-api:latest` image. Build and push the image.
3. **Health check failing:** The `/health` endpoint may not be responding. Check the task logs.
4. **Security group blocking:** The `EcsSecurityGroup` may not allow 8000 from the ALB security group.

**Fix:**
```bash
# Check ECS service status
aws ecs describe-services --cluster docintel-production-api-cluster --services docintel-production-api

# Check ECS task logs
aws logs tail /aws/ecs/docintel-production-api --follow

# Check ALB target health
aws elbv2 describe-target-health --target-group-arn <target-group-arn>
```

---

## 10. Next Steps (Phase 1)

Phase 0 is complete when:
- [x] SAM template deployed successfully
- [x] All CloudFormation resources created (S3, SQS, RDS, ElastiCache, Lambda, ECS, ALB, IAM, CloudWatch, KMS, Secrets Manager)
- [x] RDS seeded with `db/schema.sql` and `scripts/load_reference_data.py`
- [x] Lambda stub handlers deployed and tested (SQS trigger → Lambda invocation → CloudWatch log)
- [x] S3 event notification tested (upload manifest.json → SQS message → Lambda log)
- [x] CloudWatch dashboard and alarms active
- [x] NAS upload agent tested (local PDF → S3 → trigger → Lambda log)

Phase 1 begins:
- [ ] Replace Lambda stub handlers with actual pipeline code (import existing cloud/ modules)
- [ ] Build and push FastAPI Docker image to ECR (for ECS API)
- [ ] Deploy Next.js app to Vercel (pointing to ALB for API)
- [ ] Add WebSocket real-time updates (ECS API → Redis → client)
- [ ] Test end-to-end: upload PDF → S3 → OCR → Structure → Match → Persist → Index → RDS + Qdrant + Neo4j
- [ ] Run 3 test PDFs through the full pipeline and verify all data stores

**Estimated Phase 1 duration:** 2–3 weeks.

---

*Document generated: 2026-06-16*
*Version: Phase 0 — AWS Foundation*
*Stack: docintel-production (ap-south-1)*
*Status: Infrastructure deployed, stub handlers active, awaiting Phase 1 implementation.*
