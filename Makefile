.PHONY: help install up down down-clean logs db-shell init test test-integration lint format clean \
        ocr-worker stage-worker sweep upload structure match persist \
        serve web-dev web-build web-up production-test \
        aws-deploy aws-deploy-non-interactive aws-destroy aws-destroy-force aws-status \
        aws-logs aws-logs-ocr aws-logs-vlm aws-logs-structure aws-logs-match aws-logs-persist aws-logs-index \
        aws-sqs-status aws-cost-estimate \
        ecr-login build-api push-api \
        deploy-api deploy-lambdas deploy ecs-restart ecs-wait \
        upload-aws upload-aws-batch

# ── AWS config (override on command line: make deploy-api ENV=staging) ───────

REGION  ?= ap-south-1
ENV     ?= production
STACK   := docintel-$(ENV)

# Lazy: only evaluated when a recipe that uses it actually runs
ACCOUNT  = $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null)
ECR_REPO = $(ACCOUNT).dkr.ecr.$(REGION).amazonaws.com/$(STACK)-api

ECS_CLUSTER = $(STACK)-api-cluster
ECS_SERVICE = $(STACK)-api

# ────────────────────────────────────────────────────────────────────────────
# Help
# ────────────────────────────────────────────────────────────────────────────

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?##"}{printf "%-24s %s\n", $$1, $$2}'

# ────────────────────────────────────────────────────────────────────────────
# Local dev
# ────────────────────────────────────────────────────────────────────────────

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

# ────────────────────────────────────────────────────────────────────────────
# Pipeline workers (local)
# ────────────────────────────────────────────────────────────────────────────

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

# ────────────────────────────────────────────────────────────────────────────
# Tests / lint
# ────────────────────────────────────────────────────────────────────────────

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

clean:  ## Remove Python caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

# ────────────────────────────────────────────────────────────────────────────
# AWS — Push changes to production
# ────────────────────────────────────────────────────────────────────────────
#
#  Changed cloud/app.py or cloud/ Python?  →  make deploy-api
#  Changed cloud/lambda/?                  →  make deploy-lambdas
#  Changed both?                           →  make deploy
#  Changed SAM template / infra?           →  make aws-deploy-non-interactive
#

deploy-api: ## [SHIP] Build + push Docker image to ECR, then force ECS rolling update
	@echo "==> ECR login"
	@aws ecr get-login-password --region $(REGION) | docker login --username AWS --password-stdin $(ACCOUNT).dkr.ecr.$(REGION).amazonaws.com
	@echo "==> Build + push $(ECR_REPO):latest"
	@docker build -t docintel-api:latest -f cloud/Dockerfile .
	@docker tag docintel-api:latest $(ECR_REPO):latest
	@docker push $(ECR_REPO):latest
	@echo "==> Force ECS rolling update (cluster=$(ECS_CLUSTER) service=$(ECS_SERVICE))"
	@aws ecs update-service \
	  --cluster $(ECS_CLUSTER) \
	  --service $(ECS_SERVICE) \
	  --force-new-deployment \
	  --region $(REGION) \
	  --query 'service.deployments[0].{Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount}' \
	  --output table
	@echo "==> Deployment triggered. Run 'make ecs-wait' to block until stable."

deploy-lambdas: ## [SHIP] SAM build + deploy all Lambda function code changes
	sam build --template cloud/infrastructure/sam/template.yaml
	sam deploy \
	  --stack-name $(STACK) \
	  --region $(REGION) \
	  --no-confirm-changeset \
	  --no-fail-on-empty-changeset \
	  --capabilities CAPABILITY_IAM \
	  --resolve-s3
	@echo "==> Lambdas updated."

deploy: deploy-api deploy-lambdas ## [SHIP] Full redeploy: API Docker image + all Lambda functions

ecs-wait: ## Block until ECS service reaches steady state (use after deploy-api)
	@echo "==> Waiting for $(ECS_SERVICE) to stabilise..."
	@aws ecs wait services-stable \
	  --cluster $(ECS_CLUSTER) \
	  --services $(ECS_SERVICE) \
	  --region $(REGION)
	@echo "==> ECS service stable."

ecs-restart: ## Force ECS rolling restart without rebuilding image (for config/secret changes)
	aws ecs update-service \
	  --cluster $(ECS_CLUSTER) \
	  --service $(ECS_SERVICE) \
	  --force-new-deployment \
	  --region $(REGION) \
	  --query 'service.deployments[0].{Status:status,Desired:desiredCount,Running:runningCount}' \
	  --output table

# ── First-time / infra-level deploys ────────────────────────────────────────

aws-deploy:  ## [INFRA] Full SAM stack deploy — interactive (VPC prompts)
	python cloud/infrastructure/scripts/deploy.py --env $(ENV) --region $(REGION)

aws-deploy-non-interactive:  ## [INFRA] Full SAM stack deploy — non-interactive (reads env vars)
	python cloud/infrastructure/scripts/deploy.py --env $(ENV) --region $(REGION) --non-interactive

aws-destroy:  ## [INFRA] DESTROY all AWS resources (USE WITH CAUTION)
	python cloud/infrastructure/scripts/destroy.py --env $(ENV) --region $(REGION)

aws-destroy-force:  ## [INFRA] DESTROY all AWS resources — no confirmation (DANGEROUS)
	python cloud/infrastructure/scripts/destroy.py --env $(ENV) --region $(REGION) --force

# ── Low-level ECR targets (used by deploy-api; also usable standalone) ───────

ecr-login:  ## ECR docker login
	aws ecr get-login-password --region $(REGION) | docker login --username AWS --password-stdin $(ACCOUNT).dkr.ecr.$(REGION).amazonaws.com

build-api:  ## Build FastAPI Docker image locally (no push)
	docker build -t docintel-api:latest -f cloud/Dockerfile .

push-api: ecr-login build-api ## Push pre-built image to ECR (no ECS update — use deploy-api instead)
	docker tag docintel-api:latest $(ECR_REPO):latest
	docker push $(ECR_REPO):latest

# ────────────────────────────────────────────────────────────────────────────
# AWS — Observability
# ────────────────────────────────────────────────────────────────────────────

aws-status:  ## CloudFormation stack status
	aws cloudformation describe-stacks --stack-name $(STACK) --query 'Stacks[0].{Status:StackStatus,Reason:StackStatusReason}' --output table

aws-logs:  ## Tail ECS API logs
	aws logs tail /aws/ecs/$(STACK)-api --follow

aws-logs-ocr:  ## Tail OCR Lambda logs
	aws logs tail /aws/lambda/$(STACK)-ocr --follow

aws-logs-vlm:  ## Tail VLM Lambda logs
	aws logs tail /aws/lambda/$(STACK)-vlm --follow

aws-logs-structure:  ## Tail Structure Lambda logs
	aws logs tail /aws/lambda/$(STACK)-structure --follow

aws-logs-match:  ## Tail Match Lambda logs
	aws logs tail /aws/lambda/$(STACK)-match --follow

aws-logs-persist:  ## Tail Persist Lambda logs
	aws logs tail /aws/lambda/$(STACK)-persist --follow

aws-logs-index:  ## Tail Index Lambda logs
	aws logs tail /aws/lambda/$(STACK)-index --follow

aws-sqs-status:  ## Show SQS queue depths for all DocIntel queues
	@for KEY in OcrQueueUrl StructureQueueUrl MatchQueueUrl PersistQueueUrl IndexQueueUrl; do \
	  URL=$$(aws cloudformation describe-stacks --stack-name $(STACK) \
	    --query "Stacks[0].Outputs[?OutputKey==\`$$KEY\`].OutputValue | [0]" --output text); \
	  echo "$$KEY ($$URL):"; \
	  aws sqs get-queue-attributes --queue-url $$URL \
	    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
	    --output table; \
	done

# ── NAS upload ───────────────────────────────────────────────────────────────

upload-aws:  ## Upload a PDF to AWS S3 (triggers Lambda pipeline). Usage: make upload-aws PDF=path [CATEGORY=practitioner]
	python nas/upload_agent.py "$(PDF)" --category "$(or $(CATEGORY),practitioner)"

upload-aws-batch:  ## Upload all PDFs in a folder to AWS S3. Usage: make upload-aws-batch FOLDER=path [CATEGORY=practitioner] [WORKERS=4]
	python nas/upload_agent.py "$(FOLDER)" --batch --category "$(or $(CATEGORY),practitioner)" --workers "$(or $(WORKERS),4)"

# ── Cost estimate ─────────────────────────────────────────────────────────────

aws-cost-estimate:  ## Estimate monthly AWS cost for the current configuration
	@echo "DocIntel AWS Monthly Cost Estimate (ap-south-1):"
	@echo "=============================================="
	@echo "  RDS (db.t3.medium):       ~₹3,750 / ~\$$45"
	@echo "  ElastiCache (t3.micro):   ~₹1,000 / ~\$$12"
	@echo "  ECS Fargate (1 task):     ~₹1,250 / ~\$$15"
	@echo "  S3 (100 GB):              ~₹190 / ~\$$2.30"
	@echo "  Vercel (Pro):             ~₹1,250 / ~\$$15"
	@echo "  Qdrant Cloud (free):      ₹0 / \$$0"
	@echo "  Neo4j Aura (free):        ₹0 / \$$0"
	@echo "  Lambda (idle):            ₹0 / \$$0"
	@echo "  ─────────────────────────────────────"
	@echo "  Base Total (idle):        ~₹7,440 / ~\$$89"
	@echo ""
	@echo "  Per 200-document batch:"
	@echo "    Lambda OCR:             ~₹35 / ~\$$0.43"
	@echo "    Lambda VLM:             ~₹34 / ~\$$0.41"
	@echo "    Lambda (structure+match+persist+index): ~₹6 / ~\$$0.07"
	@echo "    OpenRouter API:         ~₹415 / ~\$$5.00"
	@echo "    SQS + S3 requests:      ~₹2 / ~\$$0.02"
	@echo "  ─────────────────────────────────────"
	@echo "  Batch Total:              ~₹492 / ~\$$6.00"
	@echo ""
	@echo "  200 docs/month total:     ~₹7,932 / ~\$$95"
	@echo "  2,000 docs/month total:   ~₹12,360 / ~\$$149"
	@echo "  20,000 docs/month total:  ~₹57,240 / ~\$$689 (ECS Fargate workers recommended)"

# ── AWS RDS Access ────────────────────────────────────────────────────────────

RDS_SG      ?= sg-0ceba0205d1b03e41
AWS_REGION  ?= ap-south-1

## rds-allow-ip: Add current public IP to RDS security group (port 5432)
##   Usage: make rds-allow-ip
##   Override: make rds-allow-ip MY_IP=1.2.3.4
rds-allow-ip:
	$(eval MY_IP ?= $(shell curl -s checkip.amazonaws.com))
	@echo "Adding $(MY_IP)/32 to RDS SG $(RDS_SG)..."
	aws ec2 authorize-security-group-ingress \
		--group-id $(RDS_SG) \
		--protocol tcp --port 5432 \
		--cidr $(MY_IP)/32 \
		--region $(AWS_REGION) \
		&& echo "Done — $(MY_IP)/32 can now reach RDS on port 5432." \
		|| echo "Rule may already exist (duplicate ingress rules are rejected)."

## rds-list-ips: Show all current IPs allowed into RDS on port 5432
rds-list-ips:
	aws ec2 describe-security-groups \
		--group-ids $(RDS_SG) \
		--region $(AWS_REGION) \
		--query 'SecurityGroups[0].IpPermissions[?FromPort==`5432`].IpRanges[*].CidrIp' \
		--output table
