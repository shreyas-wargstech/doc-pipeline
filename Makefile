.PHONY: help install up down down-clean logs db-shell init test test-integration lint format clean

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
