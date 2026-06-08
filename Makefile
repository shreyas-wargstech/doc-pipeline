.PHONY: help install up down down-clean logs db-shell init test test-integration lint format clean ocr-worker upload structure match persist serve web-dev web-build web-up

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?##"}{printf "%-18s %s\n", $$1, $$2}'

install:  ## Install Python deps with uv
	uv sync --extra dev

up:  ## Start local services (postgres, minio, qdrant, neo4j)
	docker compose up -d

down:  ## Stop local services (keep data volumes)
	docker compose down

down-clean:  ## Stop local services AND wipe all data volumes
	docker compose down -v

logs:  ## Tail docker logs
	docker compose logs -f

db-shell:  ## Open psql shell to local postgres
	docker compose exec postgres psql -U pipeline -d doc_pipeline

init:  ## Initialize all services (idempotent: bucket, collection, constraints)
	python -m scripts.init_all

serve:  ## Run the cloud pipeline API (local dev)
	uvicorn cloud.app:app --reload --host 0.0.0.0 --port 8000

web-dev:  ## Run the Next.js dashboard dev server (proxies /api to :8000)
	cd web && npm run dev

web-build:  ## Production build of the Next.js dashboard
	cd web && npm run build

web-up:  ## Build + start api + web containers (one origin on :3000)
	docker compose up --build api web

ocr-worker:  ## Drain the local OCR queue (elasticmq) — run alongside the pipeline
	python -m scripts.run_ocr_worker

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
