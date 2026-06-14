# AWS Orchestration (Sub-project E) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the complete document-intelligence pipeline to AWS as Lambda container images behind SQS FIFO queues, triggered by S3 ObjectCreated events on manifest.json uploads. **All datastores live inside AWS** — no external SaaS.

**Architecture:** Lambda-per-stage + SQS FIFO chaining (locked). Real S3 ObjectCreated → SQS ingest queue → ingest Lambda → per-page OCR messages → OCR Lambda → fan-in sweeper (EventBridge every 2 min) → Structure → Match → Persist → Index chain. All stages are Lambda container images in ECR. Datastores: **RDS PostgreSQL 16 (relational + pgvector vector store), Amazon Neptune Serverless (graph), real AWS S3**. Terraform manages all AWS infrastructure.

**Tech Stack:** Terraform 1.7+, AWS (Lambda, SQS FIFO, S3, RDS PostgreSQL 16 + pgvector, Amazon Neptune Serverless, ECR, EventBridge, CloudWatch, Secrets Manager, VPC/NAT), Docker (Lambda container images via `public.ecr.aws/lambda/python:3.12`).

**Locked decisions:**
- IaC: Terraform (flat single-env structure, no modules)
- **Vector store: RDS pgvector** (in-Postgres `document_pages` table, 384-dim, cosine `<=>`). Replaces Qdrant. Co-located with relational data → persist writes vectors in its own transaction; one fewer service. (See the "Datastore migration" tasks — DONE in code.)
- **Graph store: Amazon Neptune Serverless** (openCypher; MERGE-on-natural-key ports directly from Neo4j). Replaces Neo4j Aura. `GRAPH_BACKEND=neptune` makes `ensure_constraints()` a no-op (Neptune auto-indexes, rejects schema DDL).
- Lambda packaging: container images for ALL stages (uniform approach; avoids ZIP size limits; OCR and Persist/Index are heavy anyway)
- Lambda base: `public.ecr.aws/lambda/python:3.12` (Lambda RIC pre-installed)
- All queues: SQS FIFO (consistent with elasticmq local setup; per-doc/per-page dedup)
- DLQ policy: `maxReceiveCount=3` before dead-letter
- Region: `ap-south-1` (matches existing `AWS_REGION` default)
- Ingest trigger: S3 event → SQS ingest queue (standard) → ingest Lambda (reliability via SQS buffer)

**Progress (2026-06-15):**
- ✅ **Task 1 — ingest Lambda handler** (`cloud/ingest/lambda_handler.py` + tests). Committed.
- ✅ **Datastore migration (app code)** — Qdrant → pgvector, Neo4j → Neptune-ready. `cloud/persist/pgvector_writer.py`, persist/retrieval rewired, `shared/qdrant_client.py`+`qdrant_writer.py` deleted, `scripts/apply_pgvector.py`, `GRAPH_BACKEND` flag, `db/schema.sql` `document_pages` vector table. 484 unit green. Committed.
- ⬜ Remaining: Terraform infra (Tasks 2–12, revised for pgvector + Neptune below), RDS/Neptune init (Task 13), full deploy + smoke (Task 14). See `docs/AWS_SETUP.md` for the operator runbook.

---

## File Map

**New application code:**
- `cloud/ingest/lambda_handler.py` — Lambda entrypoint for S3 event → ingest (missing handler; all other stages have one)
- `tests/cloud/test_ingest_lambda_handler.py` — unit tests

**New infra directory (all new):**
```
infra/
  providers.tf          # AWS provider + S3 remote state backend
  variables.tf          # Input variables
  outputs.tf            # Exported values (queue URLs, Lambda ARNs, etc.)
  vpc.tf                # VPC, subnets, NAT gateway, security groups (lambda/rds/neptune)
  rds.tf                # RDS PostgreSQL 16 + subnet group + parameter group (pgvector)
  neptune.tf            # Amazon Neptune Serverless cluster + subnet group + instance
  secrets.tf            # Secrets Manager (DB URL, OpenRouter key, session secret)
  ecr.tf                # ECR repositories (4: ingest/ocr/light/persist-index)
  sqs.tf                # SQS FIFO queues + DLQs (ingest=standard, others=FIFO)
  iam.tf                # Lambda execution role + inline policies
  lambda.tf             # Lambda functions + event source mappings
  s3.tf                 # S3 bucket + event notification config
  eventbridge.tf        # EventBridge scheduled rule → sweeper Lambda
  monitoring.tf         # CloudWatch DLQ alarms + SNS topic
  terraform.tfvars.example

infra/docker/
  Dockerfile.ingest         # Lambda: base + PyMuPDF (manifest PDF rendering)
  Dockerfile.ocr            # Lambda: base + tesseract + tessdata + OpenCV + pyzbar
  Dockerfile.light          # Lambda: base only (structure, match, sweeper)
  Dockerfile.persist-index  # Lambda: base + torch-cpu + sentence-transformers
  build_push.sh             # Build all images + push to ECR
```

---

## Task 1: Ingest Lambda Handler — ✅ DONE (committed 6fd0e63)

**Files:**
- Create: `cloud/ingest/lambda_handler.py`
- Create: `tests/cloud/test_ingest_lambda_handler.py`

The ingest stage is the only stage without a Lambda `handler()`. All others (`cloud/ocr/consumer.py`, `cloud/structure/consumer.py`, etc.) already have one. This handler parses the S3 ObjectCreated SQS notification → reads the manifest JSON from S3 → calls `handle_manifest()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/cloud/test_ingest_lambda_handler.py
from __future__ import annotations
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from cloud.ingest.lambda_handler import handler


SAMPLE_S3_EVENT = {
    "Records": [
        {
            "eventName": "ObjectCreated:Put",
            "s3": {
                "bucket": {"name": "my-bucket"},
                "object": {"key": "documents/abc123/manifest.json"},
            },
        }
    ]
}

SAMPLE_MANIFEST_JSON = json.dumps({
    "schema_version": 1,
    "document_id": "abc123",
    "original_s3_key": "documents/abc123/original.pdf",
    "document_category": "practitioner",
    "pages": [
        {"page_num": 1, "s3_key": "documents/abc123/pages/page_001.png",
         "page_type": "form", "content_type": "typed", "language_hint": "latin"}
    ],
}).encode()


@pytest.fixture
def sqs_event():
    return {"Records": [{"messageId": "msg-1", "body": json.dumps(SAMPLE_S3_EVENT)}]}


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_happy_path(mock_s3_ctx, mock_handle, sqs_event):
    """S3 manifest event → handle_manifest called once."""
    s3_client = AsyncMock()
    resp_body = AsyncMock()
    resp_body.read = AsyncMock(return_value=SAMPLE_MANIFEST_JSON)
    s3_client.get_object = AsyncMock(return_value={"Body": resp_body})
    resp_body.__aenter__ = AsyncMock(return_value=resp_body)
    resp_body.__aexit__ = AsyncMock(return_value=False)
    s3_client.__aenter__ = AsyncMock(return_value=s3_client)
    s3_client.__aexit__ = AsyncMock(return_value=False)
    mock_s3_ctx.return_value = s3_client

    result = handler(sqs_event)

    assert result == {"batchItemFailures": []}
    mock_handle.assert_awaited_once()
    manifest_arg = mock_handle.call_args[0][0]
    assert manifest_arg.document_id == "abc123"


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_non_manifest_key_skipped(mock_s3_ctx, mock_handle):
    """Non-manifest.json S3 keys are silently skipped."""
    event = {
        "Records": [{
            "messageId": "msg-1",
            "body": json.dumps({
                "Records": [{
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "documents/abc/pages/page_001.png"},
                    },
                }]
            }),
        }]
    }
    result = handler(event)
    assert result == {"batchItemFailures": []}
    mock_handle.assert_not_awaited()


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_non_objectcreated_skipped(mock_s3_ctx, mock_handle):
    """Non-ObjectCreated event names are skipped."""
    event = {
        "Records": [{
            "messageId": "msg-1",
            "body": json.dumps({
                "Records": [{
                    "eventName": "ObjectRemoved:Delete",
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "documents/abc/manifest.json"},
                    },
                }]
            }),
        }]
    }
    result = handler(event)
    assert result == {"batchItemFailures": []}
    mock_handle.assert_not_awaited()


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_s3_read_failure_goes_to_dlq(mock_s3_ctx, mock_handle, sqs_event):
    """S3 read failure marks the record as failed (batchItemFailures)."""
    s3_client = AsyncMock()
    s3_client.get_object = AsyncMock(side_effect=Exception("S3 down"))
    s3_client.__aenter__ = AsyncMock(return_value=s3_client)
    s3_client.__aexit__ = AsyncMock(return_value=False)
    mock_s3_ctx.return_value = s3_client

    result = handler(sqs_event)

    assert result["batchItemFailures"] == [{"itemIdentifier": "msg-1"}]


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_handle_manifest_failure_goes_to_dlq(mock_s3_ctx, mock_handle, sqs_event):
    """handle_manifest failure marks the record as failed."""
    s3_client = AsyncMock()
    resp_body = AsyncMock()
    resp_body.read = AsyncMock(return_value=SAMPLE_MANIFEST_JSON)
    s3_client.get_object = AsyncMock(return_value={"Body": resp_body})
    resp_body.__aenter__ = AsyncMock(return_value=resp_body)
    resp_body.__aexit__ = AsyncMock(return_value=False)
    s3_client.__aenter__ = AsyncMock(return_value=s3_client)
    s3_client.__aexit__ = AsyncMock(return_value=False)
    mock_s3_ctx.return_value = s3_client
    mock_handle.side_effect = Exception("DB down")

    result = handler(sqs_event)

    assert result["batchItemFailures"] == [{"itemIdentifier": "msg-1"}]


def test_empty_event():
    """Empty event returns no failures."""
    result = handler({"Records": []})
    assert result == {"batchItemFailures": []}


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_url_encoded_key_decoded(mock_s3_ctx, mock_handle):
    """S3 keys with URL-encoded characters are decoded before use."""
    encoded_key = "documents/abc+123/manifest.json"
    event = {
        "Records": [{
            "messageId": "msg-1",
            "body": json.dumps({
                "Records": [{
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": encoded_key},
                    },
                }]
            }),
        }]
    }
    s3_client = AsyncMock()
    resp_body = AsyncMock()
    resp_body.read = AsyncMock(return_value=SAMPLE_MANIFEST_JSON)
    s3_client.get_object = AsyncMock(return_value={"Body": resp_body})
    resp_body.__aenter__ = AsyncMock(return_value=resp_body)
    resp_body.__aexit__ = AsyncMock(return_value=False)
    s3_client.__aenter__ = AsyncMock(return_value=s3_client)
    s3_client.__aexit__ = AsyncMock(return_value=False)
    mock_s3_ctx.return_value = s3_client

    result = handler(event)

    assert result == {"batchItemFailures": []}
    # Decoded key should be used in get_object call
    call_kwargs = s3_client.get_object.call_args[1]
    assert "+" not in call_kwargs["Key"]
```

- [ ] **Step 2: Run tests — verify they fail**

```
uv run pytest tests/cloud/test_ingest_lambda_handler.py -v
```
Expected: `ModuleNotFoundError` on `cloud.ingest.lambda_handler`

- [ ] **Step 3: Implement the handler**

```python
# cloud/ingest/lambda_handler.py
"""Ingest Lambda handler.

Trigger: SQS standard queue subscribed to S3 ObjectCreated events.
S3 sends event JSON into SQS; each SQS record body is a JSON-encoded S3 event.

Flow: SQS record → parse body as S3 event → for each S3 record with
ObjectCreated on manifest.json → read manifest from S3 → handle_manifest().

Partial-batch semantics: failed records returned in batchItemFailures so SQS
redelivers only those. handle_manifest is idempotent; redelivery is safe.
"""
from __future__ import annotations

import json
import urllib.parse

import anyio

from cloud.ingest.service import handle_manifest
from nas.manifest.models import Manifest
from shared.logging import get_logger
from shared.storage_s3 import get_s3_client

log = get_logger(__name__)


async def _process_s3_event(s3_event: dict) -> None:
    """Handle one S3 event payload (may contain multiple S3 records; usually 1)."""
    for s3_record in s3_event.get("Records", []):
        event_name: str = s3_record.get("eventName", "")
        if not event_name.startswith("ObjectCreated"):
            log.info("ingest_lambda.skip", event_name=event_name)
            continue
        bucket: str = s3_record["s3"]["bucket"]["name"]
        key: str = urllib.parse.unquote_plus(s3_record["s3"]["object"]["key"])
        if not key.endswith("/manifest.json"):
            log.info("ingest_lambda.skip", key=key, reason="not manifest.json")
            continue
        log.info("ingest_lambda.reading", bucket=bucket, key=key)
        async with get_s3_client() as s3:
            resp = await s3.get_object(Bucket=bucket, Key=key)
            async with resp["Body"] as stream:
                raw: bytes = await stream.read()
        manifest = Manifest.model_validate_json(raw)
        await handle_manifest(manifest)
        log.info("ingest_lambda.done", document_id=manifest.document_id)


async def _run_async(event: dict) -> dict:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        msg_id: str = record.get("messageId", "?")
        try:
            s3_event = json.loads(record["body"])
            await _process_s3_event(s3_event)
        except Exception:  # noqa: BLE001 — record-scoped; isolate failures
            log.exception("ingest_lambda.record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})
    return {"batchItemFailures": failures}


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint. Triggered by SQS subscribed to S3 ObjectCreated."""
    return anyio.run(_run_async, event)
```

- [ ] **Step 4: Run tests — verify they pass**

```
uv run pytest tests/cloud/test_ingest_lambda_handler.py -v
```
Expected: 7 passed

- [ ] **Step 5: Run full unit suite — verify no regressions**

```
uv run pytest -m "not integration" -q
```
Expected: all existing tests still pass (441+ green)

- [ ] **Step 6: Commit**

```
git add cloud/ingest/lambda_handler.py tests/cloud/test_ingest_lambda_handler.py
git commit -m "feat(ingest): add Lambda handler for S3 ObjectCreated event"
```

---

## Task 2: Terraform Project Scaffold

**Files:**
- Create: `infra/providers.tf`
- Create: `infra/variables.tf`
- Create: `infra/outputs.tf`
- Create: `infra/terraform.tfvars.example`

> **Pre-requisite (manual, one-time):** Create an S3 bucket for Terraform state (`terraform-state-docintel-<account_id>`) and a DynamoDB table for state locking (`terraform-state-lock`). Do this via AWS Console or a one-time `aws` CLI call before `terraform init`.

- [ ] **Step 1: Create `infra/providers.tf`**

```hcl
# infra/providers.tf
terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }

  backend "s3" {
    # Replace with your actual state bucket name and DynamoDB table
    bucket         = "terraform-state-docintel"
    key            = "doc-pipeline/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "terraform-state-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "doc-pipeline"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
```

- [ ] **Step 2: Create `infra/variables.tf`**

```hcl
# infra/variables.tf
variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Deployment environment (dev/staging/prod)"
  type        = string
  default     = "dev"
}

variable "db_password" {
  description = "Master password for RDS PostgreSQL"
  type        = string
  sensitive   = true
}

variable "openrouter_api_key" {
  description = "OpenRouter API key for VLM and LLM calls"
  type        = string
  sensitive   = true
}

variable "session_secret" {
  description = "HMAC secret for dashboard session cookies"
  type        = string
  sensitive   = true
}

# NOTE: no Qdrant/Neo4j SaaS variables — the vector store is RDS pgvector
# (same DATABASE_URL) and the graph store is Amazon Neptune (provisioned in
# neptune.tf; its endpoint is a Terraform output, not an input variable).

variable "neptune_instance_class" {
  description = "Neptune instance class (db.serverless for Serverless capacity)"
  type        = string
  default     = "db.serverless"
}

variable "neptune_min_ncu" {
  description = "Neptune Serverless minimum capacity (NCUs)"
  type        = number
  default     = 1.0
}

variable "neptune_max_ncu" {
  description = "Neptune Serverless maximum capacity (NCUs)"
  type        = number
  default     = 4.0
}

variable "s3_bucket_name" {
  description = "S3 bucket name for document storage"
  type        = string
  default     = "docintel-documents"
}

variable "ecr_image_tag" {
  description = "Docker image tag to deploy (e.g. git SHA or 'latest')"
  type        = string
  default     = "latest"
}

variable "alarm_email" {
  description = "Email address for DLQ + error CloudWatch alarms"
  type        = string
}
```

- [ ] **Step 3: Create `infra/outputs.tf`**

```hcl
# infra/outputs.tf
output "sqs_ingest_queue_url" {
  description = "URL of the ingest SQS queue (S3 → Lambda trigger)"
  value       = aws_sqs_queue.ingest.url
}

output "sqs_ocr_queue_url" {
  description = "URL of the OCR FIFO queue"
  value       = aws_sqs_queue.ocr.url
}

output "sqs_structure_queue_url" {
  description = "URL of the Structure FIFO queue"
  value       = aws_sqs_queue.structure.url
}

output "sqs_match_queue_url" {
  description = "URL of the Match FIFO queue"
  value       = aws_sqs_queue.match.url
}

output "sqs_persist_queue_url" {
  description = "URL of the Persist FIFO queue"
  value       = aws_sqs_queue.persist.url
}

output "sqs_index_queue_url" {
  description = "URL of the Index FIFO queue"
  value       = aws_sqs_queue.index.url
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (relational + pgvector vector store)"
  value       = aws_db_instance.postgres.endpoint
}

output "neptune_endpoint" {
  description = "Amazon Neptune cluster (writer) endpoint — graph store"
  value       = aws_neptune_cluster.graph.endpoint
}

output "neptune_reader_endpoint" {
  description = "Amazon Neptune reader endpoint"
  value       = aws_neptune_cluster.graph.reader_endpoint
}

output "lambda_ocr_arn" {
  description = "OCR Lambda function ARN"
  value       = aws_lambda_function.ocr.arn
}

output "lambda_sweeper_arn" {
  description = "Sweeper Lambda function ARN"
  value       = aws_lambda_function.sweeper.arn
}

output "ecr_ingest_url" {
  value = aws_ecr_repository.ingest.repository_url
}

output "ecr_ocr_url" {
  value = aws_ecr_repository.ocr.repository_url
}

output "ecr_light_url" {
  value = aws_ecr_repository.light.repository_url
}

output "ecr_persist_index_url" {
  value = aws_ecr_repository.persist_index.repository_url
}
```

- [ ] **Step 4: Create `infra/terraform.tfvars.example`**

```hcl
# infra/terraform.tfvars.example
# Copy to terraform.tfvars and fill in real values. NEVER commit terraform.tfvars.

aws_region         = "ap-south-1"
environment        = "dev"
db_password        = "CHANGE_ME_strong_password_here"
openrouter_api_key = "sk-or-..."
session_secret     = "CHANGE_ME_at_least_32_chars_random"

# Vector store = RDS pgvector (no extra vars — uses the RDS instance above).
# Graph store  = Amazon Neptune (provisioned in neptune.tf; endpoint is an
#                output, not an input). Tune Serverless capacity if needed:
neptune_min_ncu = 1.0
neptune_max_ncu = 4.0

s3_bucket_name = "docintel-documents-dev"
ecr_image_tag  = "latest"
alarm_email    = "ops@your-domain.com"
```

- [ ] **Step 5: Verify Terraform can parse the files (no actual apply)**

```bash
cd infra
terraform init -backend=false
terraform validate
```
Expected: `Success! The configuration is valid.` (partial — remaining .tf files added in later tasks)

- [ ] **Step 6: Commit**

```
git add infra/
git commit -m "feat(infra): terraform scaffold — providers, variables, outputs"
```

---

## Task 3: VPC + Networking

**Files:**
- Create: `infra/vpc.tf`

VPC layout: 2 AZs (ap-south-1a, ap-south-1b), private subnets for Lambda + RDS, no public subnets needed (Qdrant Cloud and Neo4j Aura are external SaaS — reached via NAT). NAT gateway in each AZ for Lambda egress (OpenRouter + Qdrant Cloud + Neo4j Aura calls).

- [ ] **Step 1: Create `infra/vpc.tf`**

```hcl
# infra/vpc.tf
locals {
  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "docintel-${var.environment}" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "docintel-${var.environment}-igw" }
}

# Public subnets (for NAT gateway ENIs)
resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.public_subnets[count.index]
  availability_zone = local.azs[count.index]

  tags = { Name = "docintel-${var.environment}-public-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "docintel-${var.environment}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Elastic IPs for NAT gateways
resource "aws_eip" "nat" {
  count  = 2
  domain = "vpc"
  tags   = { Name = "docintel-${var.environment}-nat-eip-${count.index + 1}" }
}

# NAT gateways (one per AZ for HA; Lambda in each private subnet can reach internet)
resource "aws_nat_gateway" "main" {
  count         = 2
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = { Name = "docintel-${var.environment}-nat-${count.index + 1}" }
  depends_on = [aws_internet_gateway.main]
}

# Private subnets (Lambda functions + RDS)
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.private_subnets[count.index]
  availability_zone = local.azs[count.index]

  tags = { Name = "docintel-${var.environment}-private-${count.index + 1}" }
}

resource "aws_route_table" "private" {
  count  = 2
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[count.index].id
  }
  tags = { Name = "docintel-${var.environment}-private-rt-${count.index + 1}" }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# Security group: Lambda functions
resource "aws_security_group" "lambda" {
  name        = "docintel-${var.environment}-lambda"
  description = "Lambda functions outbound to RDS, internet (NAT)"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound (NAT for OpenRouter/Qdrant/Neo4j; RDS SG)"
  }

  tags = { Name = "docintel-${var.environment}-lambda-sg" }
}

# Security group: RDS
resource "aws_security_group" "rds" {
  name        = "docintel-${var.environment}-rds"
  description = "RDS PostgreSQL — only reachable from Lambda SG"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
    description     = "PostgreSQL from Lambda functions"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "docintel-${var.environment}-rds-sg" }
}

# Security group: Neptune (graph store) — only reachable from Lambda SG on 8182
resource "aws_security_group" "neptune" {
  name        = "docintel-${var.environment}-neptune"
  description = "Neptune — only reachable from Lambda SG on the Bolt/openCypher port"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 8182
    to_port         = 8182
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
    description     = "Neptune (Bolt + openCypher) from Lambda functions"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "docintel-${var.environment}-neptune-sg" }
}
```

- [ ] **Step 2: Validate**

```bash
cd infra && terraform validate
```
Expected: Success

- [ ] **Step 3: Commit**

```
git add infra/vpc.tf
git commit -m "feat(infra): vpc, subnets, nat gateways, security groups"
```

---

## Task 4: RDS PostgreSQL + Secrets Manager

**Files:**
- Create: `infra/rds.tf`
- Create: `infra/secrets.tf`

RDS PostgreSQL 16 (db.t3.micro for dev; upgrade to db.t3.medium for prod). All credentials + external service URLs stored in Secrets Manager and injected into Lambda as env vars at deploy time (pulled via `terraform output` → CI/CD → Lambda env).

- [ ] **Step 1: Create `infra/rds.tf`**

```hcl
# infra/rds.tf
resource "aws_db_subnet_group" "postgres" {
  name       = "docintel-${var.environment}-postgres"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "docintel-${var.environment}-db-subnet-group" }
}

resource "aws_db_parameter_group" "postgres16" {
  name   = "docintel-${var.environment}-pg16"
  family = "postgres16"

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"  # log queries > 1s
  }

  tags = { Name = "docintel-${var.environment}-pg16-params" }
}

resource "aws_db_instance" "postgres" {
  identifier = "docintel-${var.environment}"

  engine         = "postgres"
  engine_version = "16.2"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 100  # autoscale up to 100 GB
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "doc_pipeline"
  username = "pipeline"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.postgres16.name

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  deletion_protection = false  # set true before prod
  skip_final_snapshot = true   # set false before prod

  tags = { Name = "docintel-${var.environment}-postgres" }
}
```

- [ ] **Step 2: Create `infra/secrets.tf`**

```hcl
# infra/secrets.tf
# All secrets stored in Secrets Manager; Lambda reads them at deploy time
# via the aws_secretsmanager_secret_version data source (pulled into TF outputs
# then set as Lambda env vars). Rotation deferred.

resource "aws_secretsmanager_secret" "db_url" {
  name                    = "docintel/${var.environment}/database-url"
  recovery_window_in_days = 0  # allow immediate delete in dev

  tags = { Name = "docintel-${var.environment}-db-url" }
}

resource "aws_secretsmanager_secret_version" "db_url" {
  secret_id = aws_secretsmanager_secret.db_url.id
  secret_string = jsonencode({
    DATABASE_URL = "postgresql+asyncpg://pipeline:${var.db_password}@${aws_db_instance.postgres.endpoint}/doc_pipeline"
  })

  depends_on = [aws_db_instance.postgres]
}

resource "aws_secretsmanager_secret" "openrouter" {
  name                    = "docintel/${var.environment}/openrouter"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "openrouter" {
  secret_id     = aws_secretsmanager_secret.openrouter.id
  secret_string = jsonencode({ OPENROUTER_API_KEY = var.openrouter_api_key })
}

# No Qdrant/Neo4j secrets: the vector store is RDS pgvector (DATABASE_URL above)
# and the graph store is Amazon Neptune, reached in-VPC by endpoint (an output,
# not a secret) with IAM auth disabled for dev — the SG is the access boundary.

resource "aws_secretsmanager_secret" "session" {
  name                    = "docintel/${var.environment}/session"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "session" {
  secret_id     = aws_secretsmanager_secret.session.id
  secret_string = jsonencode({ SESSION_SECRET = var.session_secret })
}

# Convenience local: all env vars needed by every Lambda
locals {
  lambda_env_vars = {
    DATABASE_URL           = jsondecode(aws_secretsmanager_secret_version.db_url.secret_string)["DATABASE_URL"]
    OPENROUTER_API_KEY     = var.openrouter_api_key
    # Vector store = pgvector in the same DATABASE_URL (no QDRANT_URL).
    # Graph store = Neptune (openCypher over Bolt+TLS). GRAPH_BACKEND=neptune
    # makes ensure_constraints() a no-op. IAM auth off → user/pass unused.
    GRAPH_BACKEND          = "neptune"
    NEO4J_URI              = "neo4j+s://${aws_neptune_cluster.graph.endpoint}:8182"
    NEO4J_USER             = "neptune"
    NEO4J_PASSWORD         = "unused"
    S3_BUCKET              = var.s3_bucket_name
    S3_REGION              = var.aws_region
    # S3_ENDPOINT_URL intentionally omitted → blank = real AWS S3
    AWS_REGION             = var.aws_region
    # SQS_ENDPOINT_URL intentionally omitted → blank = real AWS SQS
    SESSION_SECRET         = var.session_secret
    LOG_FORMAT             = "json"
    LOG_LEVEL              = "INFO"
    OPENROUTER_MODEL       = "google/gemini-2.5-flash"
    OPENROUTER_TEXT_MODEL  = "openrouter/free"
    STRUCTURE_MAX_CHARS    = "6000"
    INDEX_KEYWORD_MODE     = "llm_with_tfidf_fallback"
    RETRIEVAL_MIN_RESULTS  = "3"
  }

  # Stage-specific: add queue URLs per-Lambda in lambda.tf
  ocr_queue_url       = aws_sqs_queue.ocr.url
  structure_queue_url = aws_sqs_queue.structure.url
  match_queue_url     = aws_sqs_queue.match.url
  persist_queue_url   = aws_sqs_queue.persist.url
  index_queue_url     = aws_sqs_queue.index.url
}
```

- [ ] **Step 3: Validate**

```bash
cd infra && terraform validate
```
Expected: Success

- [ ] **Step 4: Commit**

```
git add infra/rds.tf infra/secrets.tf
git commit -m "feat(infra): rds postgres + secrets manager"
```

---

## Task 5: ECR Repositories

**Files:**
- Create: `infra/ecr.tf`

Four image variants: `ingest` (PyMuPDF), `ocr` (Tesseract + OpenCV + pyzbar), `light` (no heavy deps — used by structure, match, sweeper), `persist-index` (torch + sentence-transformers). The existing `cloud/Dockerfile` is for the API server; Lambda images are separate.

- [ ] **Step 1: Create `infra/ecr.tf`**

```hcl
# infra/ecr.tf
resource "aws_ecr_repository" "ingest" {
  name                 = "docintel-${var.environment}/ingest"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "ocr" {
  name                 = "docintel-${var.environment}/ocr"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "light" {
  name                 = "docintel-${var.environment}/light"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "persist_index" {
  name                 = "docintel-${var.environment}/persist-index"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

# Lifecycle: keep last 5 images per repo (avoid unbounded storage)
resource "aws_ecr_lifecycle_policy" "keep_last_5" {
  for_each   = toset(["ingest", "ocr", "light", "persist-index"])
  repository = "docintel-${var.environment}/${each.key}"

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })

  depends_on = [
    aws_ecr_repository.ingest,
    aws_ecr_repository.ocr,
    aws_ecr_repository.light,
    aws_ecr_repository.persist_index,
  ]
}

output "ecr_registry_id" {
  value = aws_ecr_repository.ingest.registry_id
}
```

- [ ] **Step 2: Commit**

```
git add infra/ecr.tf
git commit -m "feat(infra): ecr repositories with lifecycle policy"
```

---

## Task 6: Lambda Dockerfiles

**Files:**
- Create: `infra/docker/Dockerfile.ingest`
- Create: `infra/docker/Dockerfile.ocr`
- Create: `infra/docker/Dockerfile.light`
- Create: `infra/docker/Dockerfile.persist-index`
- Create: `infra/docker/build_push.sh`

All images use `public.ecr.aws/lambda/python:3.12` as base (Lambda RIC pre-installed, `/var/task` WORKDIR, CMD sets the handler).

**Context note:** All Dockerfiles are built from the repo ROOT (so `COPY . .` gets `shared/`, `cloud/`, `nas/`, `pyproject.toml`, `uv.lock`). Run `docker build -f infra/docker/Dockerfile.ocr .` from the repo root.

- [ ] **Step 1: Create `infra/docker/Dockerfile.ingest`**

```dockerfile
# infra/docker/Dockerfile.ingest
# Lambda image for the ingest stage (S3 event → handle_manifest → SQS OCR queue).
# Needs PyMuPDF for any PDF handling imported transitively through the codebase.
FROM public.ecr.aws/lambda/python:3.12

# System deps: PyMuPDF needs libGL-equivalent on Lambda base
RUN dnf install -y --setopt=install_weak_deps=False \
        mesa-libGL \
        glib2 \
        libzbar \
    && dnf clean all

RUN pip install --no-cache-dir uv

WORKDIR /var/task
COPY pyproject.toml uv.lock* ./
# Install deps without torch/sentence-transformers (not needed for ingest)
# uv will install from lock; the full lock includes sentence-transformers
# but we prune torch here via a minimal requirements subset.
# Simplest: install full lock, accept the size (ingest image ~1.5 GB).
RUN uv sync --frozen --no-dev

COPY shared/ shared/
COPY nas/ nas/
COPY cloud/ cloud/

CMD ["cloud.ingest.lambda_handler.handler"]
```

- [ ] **Step 2: Create `infra/docker/Dockerfile.ocr`**

```dockerfile
# infra/docker/Dockerfile.ocr
# Lambda image for the OCR stage.
# Heavy: Tesseract + tessdata (eng+mar+hin) + OpenCV + pyzbar + openai SDK.
FROM public.ecr.aws/lambda/python:3.12

RUN dnf install -y --setopt=install_weak_deps=False \
        tesseract \
        tesseract-langpack-eng \
        mesa-libGL \
        glib2 \
        zbar \
        libzbar \
    && dnf clean all

# Install Marathi + Hindi tessdata manually (not in dnf repo for Lambda AL2023)
RUN curl -L -o /usr/share/tesseract/tessdata/mar.traineddata \
        https://github.com/tesseract-ocr/tessdata/raw/main/mar.traineddata && \
    curl -L -o /usr/share/tesseract/tessdata/hin.traineddata \
        https://github.com/tesseract-ocr/tessdata/raw/main/hin.traineddata

RUN pip install --no-cache-dir uv

WORKDIR /var/task
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY shared/ shared/
COPY nas/ nas/
COPY cloud/ cloud/

CMD ["cloud.ocr.consumer.handler"]
```

- [ ] **Step 3: Create `infra/docker/Dockerfile.light`**

```dockerfile
# infra/docker/Dockerfile.light
# Lambda image for light stages: structure, match, sweeper.
# No Tesseract, no torch. Base Python + shared pipeline deps.
FROM public.ecr.aws/lambda/python:3.12

RUN dnf install -y --setopt=install_weak_deps=False \
        glib2 \
    && dnf clean all

RUN pip install --no-cache-dir uv

WORKDIR /var/task
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY shared/ shared/
COPY nas/ nas/
COPY cloud/ cloud/

# CMD is overridden per-function in Terraform via image_config.command:
# structure: cloud.structure.consumer.handler
# match:     cloud.match.consumer.handler
# sweeper:   cloud.orchestration.sweeper.handler
CMD ["cloud.structure.consumer.handler"]
```

- [ ] **Step 4: Create `infra/docker/Dockerfile.persist-index`**

```dockerfile
# infra/docker/Dockerfile.persist-index
# Lambda image for persist + index stages.
# Heavy: sentence-transformers + torch-cpu (~2.5 GB image).
# Model (paraphrase-multilingual-MiniLM-L12-v2, ~400 MB) baked in at build time
# to avoid runtime download and cold-start latency.
FROM public.ecr.aws/lambda/python:3.12

RUN dnf install -y --setopt=install_weak_deps=False \
        glib2 \
    && dnf clean all

RUN pip install --no-cache-dir uv

WORKDIR /var/task
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY shared/ shared/
COPY nas/ nas/
COPY cloud/ cloud/

# Pre-download the embedding model so no network call at cold start.
# Bakes ~400 MB into the image; avoids Lambda /tmp space issues.
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# CMD overridden per-function in Terraform:
# persist: cloud.persist.consumer.handler
# index:   cloud.index.consumer.handler
CMD ["cloud.persist.consumer.handler"]
```

- [ ] **Step 5: Create `infra/docker/build_push.sh`**

```bash
#!/usr/bin/env bash
# infra/docker/build_push.sh
# Build all Lambda container images and push to ECR.
# Usage: AWS_ACCOUNT_ID=<id> ./infra/docker/build_push.sh [image_tag]
#
# Run from repo root (Dockerfiles expect context = repo root).
set -euo pipefail

ACCOUNT="${AWS_ACCOUNT_ID:?Must set AWS_ACCOUNT_ID}"
REGION="${AWS_REGION:-ap-south-1}"
ENV="${ENVIRONMENT:-dev}"
TAG="${1:-latest}"

REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
PREFIX="docintel-${ENV}"

echo "==> Authenticating with ECR"
aws ecr get-login-password --region "${REGION}" | \
  docker login --username AWS --password-stdin "${REGISTRY}"

build_and_push() {
  local name="$1"
  local dockerfile="infra/docker/Dockerfile.${name//-/_}"
  local repo="${REGISTRY}/${PREFIX}/${name}"
  echo ""
  echo "==> Building ${name} (${dockerfile})"
  docker build -f "${dockerfile}" -t "${repo}:${TAG}" .
  echo "==> Pushing ${repo}:${TAG}"
  docker push "${repo}:${TAG}"
}

# Build order: light first (fastest sanity check), then ingest, ocr, persist-index last
build_and_push "light"
build_and_push "ingest"
build_and_push "ocr"
build_and_push "persist-index"

echo ""
echo "==> All images pushed to ECR with tag: ${TAG}"
echo ""
echo "Next: terraform apply with ecr_image_tag=${TAG}"
```

- [ ] **Step 6: Make build_push.sh executable and commit**

```bash
chmod +x infra/docker/build_push.sh
```

```
git add infra/docker/
git commit -m "feat(infra): lambda dockerfiles + ecr build/push script"
```

---

## Task 7: SQS FIFO Queues + DLQs

**Files:**
- Create: `infra/sqs.tf`
- Modify: `elasticmq.conf` (add ingest queue + missing stage queues for local dev parity)

Queue design:
- **Ingest:** standard queue (S3 event notifications require standard SQS, not FIFO)
- **OCR:** FIFO (existing; per-page dedup key = `<doc_id>:<page_num>`, 5-min window)
- **Structure/Match/Persist/Index:** FIFO (per-doc dedup key = `document_id`)
- All queues: `maxReceiveCount=3` then dead-letter to corresponding DLQ

- [ ] **Step 1: Create `infra/sqs.tf`**

```hcl
# infra/sqs.tf

# ─── Ingest queue (standard — required for S3 event notifications) ─────────
resource "aws_sqs_queue" "ingest_dlq" {
  name                      = "docintel-${var.environment}-ingest-dlq"
  message_retention_seconds = 1209600  # 14 days
}

resource "aws_sqs_queue" "ingest" {
  name                      = "docintel-${var.environment}-ingest"
  visibility_timeout_seconds = 300  # must be >= Lambda timeout
  message_retention_seconds  = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingest_dlq.arn
    maxReceiveCount     = 3
  })
}

# Allow S3 to send messages to this queue
resource "aws_sqs_queue_policy" "ingest_s3" {
  queue_url = aws_sqs_queue.ingest.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.ingest.arn
      Condition = {
        ArnLike = { "aws:SourceArn" = "arn:aws:s3:::${var.s3_bucket_name}" }
      }
    }]
  })
}

# ─── OCR FIFO queue ────────────────────────────────────────────────────────
resource "aws_sqs_queue" "ocr_dlq" {
  name       = "docintel-${var.environment}-ocr-dlq.fifo"
  fifo_queue = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "ocr" {
  name                        = "docintel-${var.environment}-ocr.fifo"
  fifo_queue                  = true
  content_based_deduplication = false  # explicit dedup IDs used by code
  visibility_timeout_seconds  = 300
  message_retention_seconds   = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ocr_dlq.arn
    maxReceiveCount     = 3
  })
}

# ─── Structure FIFO queue ──────────────────────────────────────────────────
resource "aws_sqs_queue" "structure_dlq" {
  name       = "docintel-${var.environment}-structure-dlq.fifo"
  fifo_queue = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "structure" {
  name                        = "docintel-${var.environment}-structure.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 300
  message_retention_seconds   = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.structure_dlq.arn
    maxReceiveCount     = 3
  })
}

# ─── Match FIFO queue ──────────────────────────────────────────────────────
resource "aws_sqs_queue" "match_dlq" {
  name       = "docintel-${var.environment}-match-dlq.fifo"
  fifo_queue = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "match" {
  name                        = "docintel-${var.environment}-match.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 60
  message_retention_seconds   = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.match_dlq.arn
    maxReceiveCount     = 3
  })
}

# ─── Persist FIFO queue ────────────────────────────────────────────────────
resource "aws_sqs_queue" "persist_dlq" {
  name       = "docintel-${var.environment}-persist-dlq.fifo"
  fifo_queue = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "persist" {
  name                        = "docintel-${var.environment}-persist.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 300
  message_retention_seconds   = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.persist_dlq.arn
    maxReceiveCount     = 3
  })
}

# ─── Index FIFO queue ──────────────────────────────────────────────────────
resource "aws_sqs_queue" "index_dlq" {
  name       = "docintel-${var.environment}-index-dlq.fifo"
  fifo_queue = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "index" {
  name                        = "docintel-${var.environment}-index.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 300
  message_retention_seconds   = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.index_dlq.arn
    maxReceiveCount     = 3
  })
}
```

- [ ] **Step 2: Update `elasticmq.conf` to add missing queues (local dev parity)**

```
# elasticmq.conf
include classpath("application.conf")

node-address {
    protocol = http
    host = localhost
    port = 9324
    context-path = ""
}

rest-sqs {
    enabled = true
    bind-port = 9324
    bind-hostname = "0.0.0.0"
}

queues {
    "docintel-local-ingest" {}

    "docintel-local-ocr.fifo" {
        fifo = true
        contentBasedDeduplication = false
    }

    "docintel-local-structure.fifo" {
        fifo = true
        contentBasedDeduplication = false
    }

    "docintel-local-match.fifo" {
        fifo = true
        contentBasedDeduplication = false
    }

    "docintel-local-persist.fifo" {
        fifo = true
        contentBasedDeduplication = false
    }

    "docintel-local-index.fifo" {
        fifo = true
        contentBasedDeduplication = false
    }
}
```

> **Note:** The old `ocr-queue.fifo` queue name is replaced by `docintel-local-ocr.fifo`. Update `.env` `SQS_OCR_QUEUE_URL` accordingly: `http://localhost:9324/000000000000/docintel-local-ocr.fifo`. Update all other SQS queue URLs in `.env` to match the new names.

- [ ] **Step 3: Validate**

```bash
cd infra && terraform validate
```

- [ ] **Step 4: Commit**

```
git add infra/sqs.tf elasticmq.conf
git commit -m "feat(infra): sqs fifo queues + dlqs; update elasticmq conf queue names"
```

---

## Task 8: IAM Roles + Policies

**Files:**
- Create: `infra/iam.tf`

One shared Lambda execution role. Permissions: SQS (consume + produce), S3 read (page images + manifests), Secrets Manager read, VPC networking (ENI management for VPC-attached Lambdas), CloudWatch Logs write.

- [ ] **Step 1: Create `infra/iam.tf`**

```hcl
# infra/iam.tf

# Trust policy: Lambda service can assume this role
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "docintel-${var.environment}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

# VPC networking (Lambda needs to create/manage ENIs in VPC)
resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# CloudWatch Logs (basic execution — included in VPCAccessExecutionRole, but explicit)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Inline policy: SQS, S3, Secrets Manager
data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy" "lambda_pipeline" {
  name = "docintel-${var.environment}-pipeline"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # SQS: receive/delete from all stage queues + DLQs + send to all stage queues
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:SendMessage",
          "sqs:ChangeMessageVisibility",
        ]
        Resource = [
          aws_sqs_queue.ingest.arn,
          aws_sqs_queue.ocr.arn,
          aws_sqs_queue.structure.arn,
          aws_sqs_queue.match.arn,
          aws_sqs_queue.persist.arn,
          aws_sqs_queue.index.arn,
          aws_sqs_queue.ingest_dlq.arn,
          aws_sqs_queue.ocr_dlq.arn,
          aws_sqs_queue.structure_dlq.arn,
          aws_sqs_queue.match_dlq.arn,
          aws_sqs_queue.persist_dlq.arn,
          aws_sqs_queue.index_dlq.arn,
        ]
      },
      # S3: read documents bucket (page images + manifests); no write (NAS uploads)
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:HeadObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket_name}",
          "arn:aws:s3:::${var.s3_bucket_name}/*",
        ]
      },
      # S3: write (ingest stage stores manifests; uploader doesn't use Lambda for writes,
      # but ingest consumer may need to update S3 manifest status in future)
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["arn:aws:s3:::${var.s3_bucket_name}/*"]
      },
      # Secrets Manager: read all docintel secrets
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = ["arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:docintel/${var.environment}/*"]
      },
      # ECR: pull images (Lambda pulls from ECR automatically, but explicit is safer)
      {
        Effect   = "Allow"
        Action   = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:GetAuthorizationToken",
        ]
        Resource = "*"
      },
    ]
  })
}

# EventBridge needs permission to invoke sweeper Lambda (added in eventbridge.tf)
```

- [ ] **Step 2: Commit**

```
git add infra/iam.tf
git commit -m "feat(infra): iam role + inline policies for lambda execution"
```

---

## Task 9: Lambda Functions

**Files:**
- Create: `infra/lambda.tf`

Seven Lambda functions: ingest, ocr, structure, match, persist, index, sweeper. All in VPC (private subnets) to reach RDS. All use the shared execution role. `light` image is reused for structure/match/sweeper with different `image_config.command`.

**Memory + timeout rationale:**
- `ingest`: 512 MB, 300s (classifier LLM call + per-page SQS sends)
- `ocr`: 3008 MB, 300s (Tesseract in-memory + VLM HTTP; Tesseract needs memory for tessdata)
- `structure`: 1024 MB, 300s (LLM HTTP call; JSON parse)
- `match`: 512 MB, 60s (DB read + rapidfuzz; fast)
- `persist`: 3008 MB, 300s (torch model load + Qdrant upsert + Neo4j MERGE)
- `index`: 3008 MB, 300s (torch model load + LLM + Neo4j)
- `sweeper`: 512 MB, 60s (DB read + SQS send per candidate)

- [ ] **Step 1: Create `infra/lambda.tf`**

```hcl
# infra/lambda.tf

locals {
  ecr_registry = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"

  ingest_image       = "${aws_ecr_repository.ingest.repository_url}:${var.ecr_image_tag}"
  ocr_image          = "${aws_ecr_repository.ocr.repository_url}:${var.ecr_image_tag}"
  light_image        = "${aws_ecr_repository.light.repository_url}:${var.ecr_image_tag}"
  persist_idx_image  = "${aws_ecr_repository.persist_index.repository_url}:${var.ecr_image_tag}"

  vpc_config = {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  # Env vars shared by all stages + stage-specific queue URLs merged per-function
  base_env = merge(local.lambda_env_vars, {
    SQS_OCR_QUEUE_URL       = aws_sqs_queue.ocr.url
    SQS_STRUCTURE_QUEUE_URL = aws_sqs_queue.structure.url
    SQS_MATCH_QUEUE_URL     = aws_sqs_queue.match.url
    SQS_PERSIST_QUEUE_URL   = aws_sqs_queue.persist.url
    SQS_INDEX_QUEUE_URL     = aws_sqs_queue.index.url
  })
}

# ─── Ingest Lambda ─────────────────────────────────────────────────────────
resource "aws_lambda_function" "ingest" {
  function_name = "docintel-${var.environment}-ingest"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.ingest_image
  timeout       = 300
  memory_size   = 512

  image_config {
    command = ["cloud.ingest.lambda_handler.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_config.subnet_ids
    security_group_ids = local.vpc_config.security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "ingest" }
}

# ─── OCR Lambda ────────────────────────────────────────────────────────────
resource "aws_lambda_function" "ocr" {
  function_name = "docintel-${var.environment}-ocr"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.ocr_image
  timeout       = 300
  memory_size   = 3008

  image_config {
    command = ["cloud.ocr.consumer.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_config.subnet_ids
    security_group_ids = local.vpc_config.security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "ocr" }
}

# ─── Structure Lambda ──────────────────────────────────────────────────────
resource "aws_lambda_function" "structure" {
  function_name = "docintel-${var.environment}-structure"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.light_image
  timeout       = 300
  memory_size   = 1024

  image_config {
    command = ["cloud.structure.consumer.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_config.subnet_ids
    security_group_ids = local.vpc_config.security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "structure" }
}

# ─── Match Lambda ──────────────────────────────────────────────────────────
resource "aws_lambda_function" "match" {
  function_name = "docintel-${var.environment}-match"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.light_image
  timeout       = 60
  memory_size   = 512

  image_config {
    command = ["cloud.match.consumer.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_config.subnet_ids
    security_group_ids = local.vpc_config.security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "match" }
}

# ─── Persist Lambda ────────────────────────────────────────────────────────
resource "aws_lambda_function" "persist" {
  function_name = "docintel-${var.environment}-persist"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.persist_idx_image
  timeout       = 300
  memory_size   = 3008

  image_config {
    command = ["cloud.persist.consumer.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_config.subnet_ids
    security_group_ids = local.vpc_config.security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "persist" }
}

# ─── Index Lambda ──────────────────────────────────────────────────────────
resource "aws_lambda_function" "index" {
  function_name = "docintel-${var.environment}-index"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.persist_idx_image
  timeout       = 300
  memory_size   = 3008

  image_config {
    command = ["cloud.index.consumer.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_config.subnet_ids
    security_group_ids = local.vpc_config.security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "index" }
}

# ─── Sweeper Lambda ────────────────────────────────────────────────────────
resource "aws_lambda_function" "sweeper" {
  function_name = "docintel-${var.environment}-sweeper"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.light_image
  timeout       = 60
  memory_size   = 512

  image_config {
    command = ["cloud.orchestration.sweeper.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_config.subnet_ids
    security_group_ids = local.vpc_config.security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "sweeper" }
}

# ─── Event Source Mappings (SQS → Lambda) ─────────────────────────────────
# ReportBatchItemFailures enabled on all — consumers return batchItemFailures
# so only failed records are redelivered (not the whole batch).

resource "aws_lambda_event_source_mapping" "ingest" {
  event_source_arn                   = aws_sqs_queue.ingest.arn
  function_name                      = aws_lambda_function.ingest.arn
  batch_size                         = 1  # one manifest at a time
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "ocr" {
  event_source_arn                   = aws_sqs_queue.ocr.arn
  function_name                      = aws_lambda_function.ocr.arn
  batch_size                         = 5  # process up to 5 pages per invocation
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "structure" {
  event_source_arn                   = aws_sqs_queue.structure.arn
  function_name                      = aws_lambda_function.structure.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "match" {
  event_source_arn                   = aws_sqs_queue.match.arn
  function_name                      = aws_lambda_function.match.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "persist" {
  event_source_arn                   = aws_sqs_queue.persist.arn
  function_name                      = aws_lambda_function.persist.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "index" {
  event_source_arn                   = aws_sqs_queue.index.arn
  function_name                      = aws_lambda_function.index.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}
```

- [ ] **Step 2: Validate**

```bash
cd infra && terraform validate
```
Expected: Success

- [ ] **Step 3: Commit**

```
git add infra/lambda.tf
git commit -m "feat(infra): lambda functions + sqs event source mappings"
```

---

## Task 10: S3 Bucket + Event Notification

**Files:**
- Create: `infra/s3.tf`

The existing MinIO-compatible S3 code will work unchanged against real AWS S3 — `shared/storage_s3.py` uses `S3_ENDPOINT_URL` (blank = real AWS). The S3 bucket receives `ObjectCreated` events on `documents/*/manifest.json` and fans them into the ingest SQS queue.

- [ ] **Step 1: Create `infra/s3.tf`**

```hcl
# infra/s3.tf

resource "aws_s3_bucket" "documents" {
  bucket = var.s3_bucket_name

  tags = { Name = "docintel-${var.environment}-documents" }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 → SQS notification: only manifest.json uploads trigger ingest
resource "aws_s3_bucket_notification" "manifest_created" {
  bucket = aws_s3_bucket.documents.id

  queue {
    id            = "manifest-created"
    queue_arn     = aws_sqs_queue.ingest.arn
    events        = ["s3:ObjectCreated:*"]
    filter_suffix = "/manifest.json"
  }

  depends_on = [aws_sqs_queue_policy.ingest_s3]
}
```

- [ ] **Step 2: Validate**

```bash
cd infra && terraform validate
```

- [ ] **Step 3: Commit**

```
git add infra/s3.tf
git commit -m "feat(infra): s3 bucket + manifest objectcreated notification to ingest queue"
```

---

## Task 11: EventBridge Sweeper + Lambda Permission

**Files:**
- Create: `infra/eventbridge.tf`

EventBridge rule fires every 2 minutes → invokes the sweeper Lambda. The sweeper checks for documents in `processing` status with all pages done and advances them to `structuring` + enqueues to Structure queue.

- [ ] **Step 1: Create `infra/eventbridge.tf`**

```hcl
# infra/eventbridge.tf

resource "aws_cloudwatch_event_rule" "sweeper" {
  name                = "docintel-${var.environment}-sweeper"
  description         = "Fan-in: advance OCR-complete documents to Structure queue"
  schedule_expression = "rate(2 minutes)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "sweeper_lambda" {
  rule      = aws_cloudwatch_event_rule.sweeper.name
  target_id = "SweepLambda"
  arn       = aws_lambda_function.sweeper.arn
}

# Grant EventBridge permission to invoke the sweeper Lambda
resource "aws_lambda_permission" "eventbridge_sweeper" {
  statement_id  = "AllowEventBridgeSweeper"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sweeper.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sweeper.arn
}
```

- [ ] **Step 2: Commit**

```
git add infra/eventbridge.tf
git commit -m "feat(infra): eventbridge rule triggers sweeper every 2 minutes"
```

---

## Task 12: CloudWatch Alarms + SNS

**Files:**
- Create: `infra/monitoring.tf`

DLQ depth alarms: any message landing in a DLQ means a document/page failed 3 retries — trigger an SNS email alert. Also alarm on Lambda error rate for fast feedback.

- [ ] **Step 1: Create `infra/monitoring.tf`**

```hcl
# infra/monitoring.tf

resource "aws_sns_topic" "alerts" {
  name = "docintel-${var.environment}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# Helper: DLQ depth alarm for any queue
locals {
  dlqs = {
    ingest    = aws_sqs_queue.ingest_dlq.name
    ocr       = aws_sqs_queue.ocr_dlq.name
    structure = aws_sqs_queue.structure_dlq.name
    match     = aws_sqs_queue.match_dlq.name
    persist   = aws_sqs_queue.persist_dlq.name
    index     = aws_sqs_queue.index_dlq.name
  }
}

resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  for_each = local.dlqs

  alarm_name          = "docintel-${var.environment}-${each.key}-dlq-nonempty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "DLQ ${each.value} has messages — document failed 3 retries"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = each.value
  }
}

# Lambda error rate alarm per stage
locals {
  lambda_names = {
    ingest    = aws_lambda_function.ingest.function_name
    ocr       = aws_lambda_function.ocr.function_name
    structure = aws_lambda_function.structure.function_name
    match     = aws_lambda_function.match.function_name
    persist   = aws_lambda_function.persist.function_name
    index     = aws_lambda_function.index.function_name
    sweeper   = aws_lambda_function.sweeper.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.lambda_names

  alarm_name          = "docintel-${var.environment}-${each.key}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Lambda ${each.value} has >5 errors in 5 min"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = each.value
  }
}
```

- [ ] **Step 2: Commit**

```
git add infra/monitoring.tf
git commit -m "feat(infra): cloudwatch dlq alarms + lambda error alerts via sns"
```

---

## Task 13: Schema + Reference Data Setup on RDS

One-time tasks to initialise the RDS instance after `terraform apply` provisions it. These run from a machine that can reach the RDS endpoint (bastion, developer VPN, or a temporary Lambda).

- [ ] **Step 1: Confirm RDS endpoint is reachable**

From a machine with VPN/bastion access to the VPC private subnet, or temporarily making RDS publicly accessible (change `publicly_accessible = true` in `rds.tf`, `terraform apply`, then revert):

```bash
psql "postgresql://pipeline:<DB_PASSWORD>@<RDS_ENDPOINT>:5432/doc_pipeline" -c "SELECT version();"
```
Expected: PostgreSQL 16.x

- [ ] **Step 2: Apply schema**

```bash
psql "postgresql://pipeline:<DB_PASSWORD>@<RDS_ENDPOINT>:5432/doc_pipeline" \
     -f db/schema.sql
```
Expected: all tables created (documents, pages, reference_data, dashboard_users, audit_log, cost_events, eval_content_type, document_bookmarks, page_types)

- [ ] **Step 3: Apply cost_events migration**

```bash
DATABASE_URL="postgresql+asyncpg://pipeline:<DB_PASSWORD>@<RDS_ENDPOINT>/doc_pipeline" \
  uv run python -m scripts.apply_cost_events
```

- [ ] **Step 4: Load reference data**

```bash
DATABASE_URL="postgresql+asyncpg://pipeline:<DB_PASSWORD>@<RDS_ENDPOINT>/doc_pipeline" \
  uv run python -m scripts.load_reference_data
```
Expected: 92,389 rows loaded

- [ ] **Step 5: Add dashboard user**

```bash
DATABASE_URL="postgresql+asyncpg://pipeline:<DB_PASSWORD>@<RDS_ENDPOINT>/doc_pipeline" \
  uv run python -m scripts.add_dashboard_user
```

- [ ] **Step 6: Confirm Qdrant Cloud + Neo4j Aura connectivity**

In Qdrant Cloud console (`cloud.qdrant.io`): create a cluster, copy the URL + API key → put in `terraform.tfvars`.

In Neo4j Aura console (`console.neo4j.io`): create a free instance, copy the connection URI + password → put in `terraform.tfvars`.

Test connectivity:
```python
# Quick connectivity check — run locally after setting env vars
from qdrant_client import QdrantClient
c = QdrantClient(url="<QDRANT_URL>", api_key="<QDRANT_API_KEY>")
print(c.get_collections())

from neo4j import GraphDatabase
d = GraphDatabase.driver("<NEO4J_URI>", auth=("<NEO4J_USER>", "<NEO4J_PASSWORD>"))
d.verify_connectivity()
print("Neo4j OK")
```

Run `python -m scripts.init_qdrant` and `python -m scripts.init_neo4j` with cloud env vars to create the collection and constraints.

---

## Task 14: Full Deploy + Smoke Test

- [ ] **Step 1: Build and push all Lambda images**

```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=ap-south-1
export ENVIRONMENT=dev
./infra/docker/build_push.sh latest
```
Expected: all 4 images pushed to ECR (`ingest`, `ocr`, `light`, `persist-index`)

- [ ] **Step 2: First `terraform apply`**

```bash
cd infra
terraform init
terraform plan -var-file=terraform.tfvars -out=tfplan
terraform apply tfplan
```
Expected: ~50+ resources created. Note the outputs:
```
sqs_ingest_queue_url    = "https://sqs.ap-south-1.amazonaws.com/<account>/docintel-dev-ingest"
sqs_ocr_queue_url       = "https://sqs.ap-south-1.amazonaws.com/<account>/docintel-dev-ocr.fifo"
rds_endpoint            = "docintel-dev.xxxx.ap-south-1.rds.amazonaws.com:5432"
...
```

- [ ] **Step 3: Verify Lambda functions exist and are active**

```bash
aws lambda list-functions --query "Functions[?starts_with(FunctionName,'docintel-dev')].[FunctionName,State]" \
  --output table
```
Expected: 7 rows, all `State=Active`

- [ ] **Step 4: Upload one test bundle via NAS uploader (real S3)**

Update local `.env` to point at real AWS (blank out `S3_ENDPOINT_URL`, `SQS_ENDPOINT_URL`; set real `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`; set real SQS queue URLs from Terraform output):

```bash
# .env additions for AWS smoke test
S3_ENDPOINT_URL=
SQS_ENDPOINT_URL=
SQS_OCR_QUEUE_URL=<from terraform output sqs_ocr_queue_url>
SQS_STRUCTURE_QUEUE_URL=<from terraform output sqs_structure_queue_url>
SQS_MATCH_QUEUE_URL=<from terraform output sqs_match_queue_url>
SQS_PERSIST_QUEUE_URL=<from terraform output sqs_persist_queue_url>
SQS_INDEX_QUEUE_URL=<from terraform output sqs_index_queue_url>
DATABASE_URL=postgresql+asyncpg://pipeline:<DB_PASSWORD>@<RDS_ENDPOINT>/doc_pipeline
QDRANT_URL=<qdrant cloud url>
NEO4J_URI=<neo4j aura uri>
```

Upload one bundle:
```bash
uv run python -m scripts.upload_pdf HomoeoFiles_local/AMR-MCH-26-A-07723.pdf \
  --trigger direct --category practitioner
```
Expected: `upload.done` log — original PDF + 15 page PNGs + manifest.json in S3.

- [ ] **Step 5: Watch ingest Lambda fire**

The manifest.json upload triggers S3 → SQS ingest queue → ingest Lambda automatically.

```bash
aws logs tail /aws/lambda/docintel-dev-ingest --since 5m --follow
```
Expected logs: `ingest_lambda.reading`, `ingest.classify`, `ingest.enqueued`, `ingest_lambda.done`

- [ ] **Step 6: Watch OCR Lambda drain**

```bash
aws logs tail /aws/lambda/docintel-dev-ocr --since 5m --follow
```
Expected: 13 `ocr.done` log entries (non-blank pages from 15-page bundle); `ocr_status` updates in RDS.

- [ ] **Step 7: Verify sweeper fires and advances document**

Within 2 minutes of last OCR page, EventBridge fires sweeper:
```bash
aws logs tail /aws/lambda/docintel-dev-sweeper --since 5m
```
Expected: `sweep_done` with `advanced=1`; `documents.status` → `structuring` in RDS.

- [ ] **Step 8: Watch Structure → Match → Persist → Index chain**

```bash
for stage in structure match persist index; do
  echo "=== $stage ==="
  aws logs tail /aws/lambda/docintel-dev-$stage --since 10m
done
```
Expected: each stage logs completion; final `documents.status='processed'` in RDS.

- [ ] **Step 9: Verify all 4 datastores**

```sql
-- RDS: document processed
SELECT status, match_status FROM documents WHERE document_id='<doc_id>';
-- Expected: status=processed, match_status=matched (or unmatched if reg_no not in reference_data)
```

```bash
# Qdrant: identity page vectors present
python -c "
from qdrant_client import QdrantClient
c = QdrantClient(url='<QDRANT_URL>', api_key='<QDRANT_API_KEY>')
print(c.count('document_pages'))
"
```

```cypher
// Neo4j: document + pages persisted
MATCH (d:Document {document_id: '<doc_id>'})-[:HAS_PAGE]->(p:Page)
RETURN d.status, count(p);
```

```bash
# S3: all objects present
aws s3 ls s3://<bucket>/documents/<doc_id>/ --recursive | wc -l
# Expected: 17 objects (original.pdf + 15 page PNGs + manifest.json)
```

- [ ] **Step 10: Commit session log + TASKS.md update**

Update `documentation/session_log.md` and `documentation/TASKS.md` (check off P2 AWS orchestration item) and commit.

---

## Self-Review Checklist

**Spec coverage:**
- [x] S3 event → ingest Lambda (Task 1 + Task 10)
- [x] SQS FIFO queues per stage (Task 7)
- [x] Lambda per stage (Task 9)
- [x] Event source mappings + ReportBatchItemFailures (Task 9)
- [x] VPC + NAT for Lambda egress to Qdrant Cloud / Neo4j Aura / OpenRouter (Task 3)
- [x] RDS PostgreSQL (Task 4)
- [x] Secrets Manager (Task 4)
- [x] ECR per image variant (Task 5)
- [x] Lambda container images (Task 6)
- [x] EventBridge → sweeper (Task 11)
- [x] DLQs + CloudWatch alarms (Task 7 + Task 12)
- [x] IaC tool decided: Terraform (Task 2)
- [x] Qdrant hosting decided: Qdrant Cloud (Task 13)
- [x] Neo4j hosting decided: Neo4j Aura (Task 13)
- [x] torch/MiniLM on Lambda: persist-index image bakes model in (Task 6)
- [x] Smoke test end-to-end (Task 14)

**Placeholder scan:** None found.

**Type consistency:**
- `cloud.ingest.lambda_handler.handler` matches the function defined in Task 1
- `aws_sqs_queue.ingest.url` referenced in `sqs.tf` and used in `s3.tf` `depends_on`
- `aws_ecr_repository.ingest.repository_url` referenced in `lambda.tf` local
- `local.base_env` defined in `secrets.tf` used in `lambda.tf`
- `local.vpc_config` defined in `lambda.tf` reused across all 7 functions
- `data.aws_caller_identity.current` defined in `iam.tf`, referenced in `lambda.tf` — both `.tf` files load in same plan; no ordering issue

**Open items NOT in scope of this plan (document in TASKS.md):**
- NAS → real S3 batch upload script (`scripts/batch_upload.py`) for 200+ doc runs
- `S3PrefixSource` drop-in for AWS production folder runs
- Persisted run history (Approach B) for the folder runner
- Per-stage latency tracking in cost_events
- Lambda SnapStart for persist/index (reduce cold start once model is proven stable)
- Multi-AZ RDS + deletion_protection=true before production promotion
- Terraform remote state bucket bootstrap (one-time manual creation)
