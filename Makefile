.PHONY: help install up down down-clean logs db-shell init test test-integration lint format clean ocr-worker upload structure match persist serve web-dev web-build web-up aws-deploy aws-destroy aws-status aws-logs ecr-login build-api push-api

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?##"}{printf "%-18s %s\n", $$1, $$2}'

install:  ## Install Python deps with uv
	uv sync --extra dev

up:  ## Start local services (postgres, minio, qdrant, neo4j)
	docker compose up -d postgres minio neo4j qdrant elasticmq

down:  ## Stop local services (keep data volumes)
	docker compose down

status: ## Show status of local services
	docker compose ps

down-clean:  ## Stop local services AND wipe all data volumes
	docker compose down -v

logs:  ## Tail docker logs
	docker compose logs -f

db-shell:  ## Open psql shell to local postgres
	docker compose exec postgres psql -U pipeline -d doc_pipeline

init:  ## Initialize all services (idempotent: bucket, collection, constraints)
	python -m scripts.init_all

serve:  ## Run the cloud pipeline API (local dev)
	uvicorn cloud.app:app --reload --reload-dir cloud --reload-dir shared --host 0.0.0.0 --port 8000

web-dev:  ## Run the Next.js dashboard dev server (proxies /api to :8000)
	cd web && npm run dev

web-build:  ## Production build of the Next.js dashboard
	cd web && npm run build

web-up:  ## Build + start api + web containers (one origin on :3000)
	docker compose up --build api web

ocr-worker:  ## Drain the local OCR queue (elasticmq) — run alongside the pipeline
	python -m scripts.run_ocr_worker

stage-worker:  ## Drain one stage queue. Usage: make stage-worker STAGE=structure|match|persist
	uv run python -m scripts.run_stage_worker --stage $(STAGE)

sweep:  ## Run one fan-in sweep (advance OCR-complete docs to Structure)
	uv run python -m scripts.run_sweeper

production-test:  ## One-shot end-to-end test against real AWS queues
	uv run python -m scripts.run_production_test

upload:  ## Upload a PDF end-to-end. Usage: make upload PDF=path [CATEGORY=practitioner] [TRIGGER=direct]
	python -m scripts.upload_pdf "$(PDF)" --category "$(or $(CATEGORY),practitioner)" --trigger "$(or $(TRIGGER),direct)"

structure:  ## Run the Structure stage on one document. Usage: make structure DOC=<document_id>
	python -m scripts.run_structure --document-id "$(DOC)"

match:  ## Run the Match stage on one document. Usage: make match DOC=<document_id>
	python -m scripts.run_match --document-id "$(DOC)"

persist:  ## Run the Persist stage on one document. Usage: make persist DOC=<document_id>
	python -m scripts.run_persist --document-id "$(DOC)"

test:  ## Run unit tests only
	pytest -v -m "not integration"

test-integration:  ## Run integration tests (requires `make up` + `make init`)
	pytest -v -m integration

lint:  ## Run ruff + mypy
	ruff check .
	mypy .

format:  ## Format with ruff
	ruff format .
	ruff check --fix .

clean:  ## Remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
clean:  ## Remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

# ────────────────────────────────────────────────────────────────────────────
# AWS Infrastructure Targets (Phase 0 — Zero Docker, Full Managed Services)
# ────────────────────────────────────────────────────────────────────────────

aws-deploy:  ## Deploy DocIntel stack to AWS (interactive, prompts for VPC + credentials)
	python cloud/infrastructure/scripts/deploy.py --env production --region ap-south-1

aws-deploy-non-interactive:  ## Deploy DocIntel stack to AWS (non-interactive, reads env vars)
	python cloud/infrastructure/scripts/deploy.py --env production --region ap-south-1 --non-interactive

aws-destroy:  ## DESTROY all DocIntel AWS resources (USE WITH CAUTION)
	python cloud/infrastructure/scripts/destroy.py --env production --region ap-south-1

aws-destroy-force:  ## DESTROY all DocIntel AWS resources (NO CONFIRMATION — DANGEROUS)
	python cloud/infrastructure/scripts/destroy.py --env production --region ap-south-1 --force

aws-status:  ## Show CloudFormation stack status
	aws cloudformation describe-stacks --stack-name docintel-production --query 'Stacks[0].{Status:StackStatus,Reason:StackStatusReason}' --output table

aws-logs:  ## Tail CloudWatch logs for the API ECS service
	aws logs tail /aws/ecs/docintel-production-api --follow

aws-logs-ocr:  ## Tail CloudWatch logs for the OCR Lambda
	aws logs tail /aws/lambda/docintel-production-ocr --follow

aws-logs-vlm:  ## Tail CloudWatch logs for the VLM Lambda
	aws logs tail /aws/lambda/docintel-production-vlm --follow

aws-logs-structure:  ## Tail CloudWatch logs for the Structure Lambda
	aws logs tail /aws/lambda/docintel-production-structure --follow

aws-logs-match:  ## Tail CloudWatch logs for the Match Lambda
	aws logs tail /aws/lambda/docintel-production-match --follow

aws-logs-persist:  ## Tail CloudWatch logs for the Persist Lambda
	aws logs tail /aws/lambda/docintel-production-persist --follow

aws-logs-index:  ## Tail CloudWatch logs for the Index Lambda
	aws logs tail /aws/lambda/docintel-production-index --follow

aws-sqs-status:  ## Show SQS queue depths for all DocIntel queues
	@echo "OCR Queue:"
	aws sqs get-queue-attributes --queue-url $$(aws cloudformation describe-stacks --stack-name docintel-production --query 'Stacks[0].Outputs[?OutputKey==`OcrQueueUrl`].OutputValue | [0]' --output text) --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
	@echo "Structure Queue:"
	aws sqs get-queue-attributes --queue-url $$(aws cloudformation describe-stacks --stack-name docintel-production --query 'Stacks[0].Outputs[?OutputKey==`StructureQueueUrl`].OutputValue | [0]' --output text) --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
	@echo "Match Queue:"
	aws sqs get-queue-attributes --queue-url $$(aws cloudformation describe-stacks --stack-name docintel-production --query 'Stacks[0].Outputs[?OutputKey==`MatchQueueUrl`].OutputValue | [0]' --output text) --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
	@echo "Persist Queue:"
	aws sqs get-queue-attributes --queue-url $$(aws cloudformation describe-stacks --stack-name docintel-production --query 'Stacks[0].Outputs[?OutputKey==`PersistQueueUrl`].OutputValue | [0]' --output text) --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
	@echo "Index Queue:"
	aws sqs get-queue-attributes --queue-url $$(aws cloudformation describe-stacks --stack-name docintel-production --query 'Stacks[0].Outputs[?OutputKey==`IndexQueueUrl`].OutputValue | [0]' --output text) --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible

# ── Docker Image for ECS API (Phase 2) ──────────────────────────────────────

ecr-login:  ## Log in to Amazon ECR (needed before pushing Docker image)
	aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin $$(aws sts get-caller-identity --query Account --output text).dkr.ecr.ap-south-1.amazonaws.com

build-api:  ## Build the FastAPI Docker image for ECS deployment
	docker build -t docintel-api:latest -f cloud/Dockerfile .

push-api:  ## Build + tag + push the FastAPI Docker image to ECR (requires ecr-login)
	@echo "Building API image..."
	@ACCOUNT=$$(aws sts get-caller-identity --query Account --output text); \
	ECR_REPO=$$ACCOUNT.dkr.ecr.ap-south-1.amazonaws.com/docintel-production-api; \
	docker build -t docintel-api:latest -f cloud/Dockerfile . && \
	docker tag docintel-api:latest $$ECR_REPO:latest && \
	docker push $$ECR_REPO:latest

# ── NAS Upload Agent (Zero Docker) ───────────────────────────────────────────

upload-aws:  ## Upload a PDF to AWS S3 (triggers Lambda pipeline). Usage: make upload-aws PDF=path [CATEGORY=practitioner]
	python nas/upload_agent.py "$(PDF)" --category "$(or $(CATEGORY),practitioner)"

upload-aws-batch:  ## Upload all PDFs in a folder to AWS S3. Usage: make upload-aws-batch FOLDER=path [CATEGORY=practitioner] [WORKERS=4]
	python nas/upload_agent.py "$(FOLDER)" --batch --category "$(or $(CATEGORY),practitioner)" --workers "$(or $(WORKERS),4)"

# ── Utility ─────────────────────────────────────────────────────────────────

aws-cost-estimate:  ## Estimate monthly AWS cost for the current configuration
	@echo "DocIntel AWS Monthly Cost Estimate (ap-south-1):"
	@echo "=============================================="
	@echo "  RDS (db.t3.medium):       ~₹3,750 / ~$45"
	@echo "  ElastiCache (t3.micro):   ~₹1,000 / ~$12"
	@echo "  ECS Fargate (1 task):     ~₹1,250 / ~$15"
	@echo "  S3 (100 GB):              ~₹190 / ~$2.30"
	@echo "  Vercel (Pro):             ~₹1,250 / ~$15"
	@echo "  Qdrant Cloud (free):      ₹0 / $0"
	@echo "  Neo4j Aura (free):        ₹0 / $0"
	@echo "  Lambda (idle):            ₹0 / $0"
	@echo "  ─────────────────────────────────────"
	@echo "  Base Total (idle):        ~₹7,440 / ~$89"
	@echo ""
	@echo "  Per 200-document batch:"
	@echo "    Lambda OCR:             ~₹35 / ~$0.43"
	@echo "    Lambda VLM:             ~₹34 / ~$0.41"
	@echo "    Lambda (structure+match+persist+index): ~₹6 / ~$0.07"
	@echo "    OpenRouter API:         ~₹415 / ~$5.00"
	@echo "    SQS + S3 requests:      ~₹2 / ~$0.02"
	@echo "  ─────────────────────────────────────"
	@echo "  Batch Total:              ~₹492 / ~$6.00"
	@echo ""
	@echo "  200 docs/month total:     ~₹7,932 / ~$95"
	@echo "  2,000 docs/month total:   ~₹12,360 / ~$149"
	@echo "  20,000 docs/month total:  ~₹57,240 / ~$689 (ECS Fargate workers recommended)"
