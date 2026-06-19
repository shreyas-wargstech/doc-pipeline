"""Shared configuration loaded from environment variables."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = Field(..., alias="DATABASE_URL")

    # S3 / MinIO
    s3_endpoint_url: str | None = Field(None, alias="S3_ENDPOINT_URL")
    s3_access_key: str = Field("", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field("", alias="S3_SECRET_KEY")
    s3_bucket: str = Field(..., alias="S3_BUCKET")
    s3_region: str = Field("us-east-1", alias="S3_REGION")

    # Qdrant
    qdrant_url: str = Field(..., alias="QDRANT_URL")
    qdrant_api_key: str = Field("", alias="QDRANT_API_KEY")
    qdrant_collection: str = Field("document_pages", alias="QDRANT_COLLECTION")
    embedding_model: str = Field(
        "paraphrase-multilingual-MiniLM-L12-v2", alias="EMBEDDING_MODEL"
    )

    # Neo4j
    neo4j_uri: str = Field(..., alias="NEO4J_URI")
    neo4j_user: str = Field(..., alias="NEO4J_USER")
    # Optional so get_settings() succeeds in Lambda (env can't reference Secrets
    # Manager); get_driver() loads it from Secrets Manager at runtime when empty.
    neo4j_password: str = Field("", alias="NEO4J_PASSWORD")

    # OCR
    ocr_confidence_threshold: int = Field(70, alias="OCR_CONFIDENCE_THRESHOLD")

    # Logging
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_format: str = Field("json", alias="LOG_FORMAT")

    # SQS
    sqs_ocr_queue_url: str = Field(..., alias="SQS_OCR_QUEUE_URL")
    aws_region: str = Field("ap-south-1", alias="AWS_REGION")
    sqs_endpoint_url: str = Field("", alias="SQS_ENDPOINT_URL")
    sqs_structure_queue_url: str = Field("", alias="SQS_STRUCTURE_QUEUE_URL")
    sqs_match_queue_url: str = Field("", alias="SQS_MATCH_QUEUE_URL")
    sqs_persist_queue_url: str = Field("", alias="SQS_PERSIST_QUEUE_URL")
    sqs_index_queue_url: str = Field("", alias="SQS_INDEX_QUEUE_URL")

    # Index stage
    index_keyword_mode: str = Field(
        "llm_with_tfidf_fallback", alias="INDEX_KEYWORD_MODE"
    )  # "llm" | "tfidf" | "llm_with_tfidf_fallback"

    # Retrieval cascade
    retrieval_min_results: int = Field(3, alias="RETRIEVAL_MIN_RESULTS")

    # OpenRouter (cloud OCR tier — VLM via OpenAI-compatible gateway)
    openrouter_api_key: str | None = Field(None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        "https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    # Vision model — used by VlmTier (handwriting OCR) + VlmPageTyper (image classify).
    openrouter_model: str = Field(
        "google/gemini-2.5-flash", alias="OPENROUTER_MODEL"
    )
    # Text-only model — used by classifier LLM + structure LLM (no image input).
    # Defaults to openrouter/free (auto-selects a working free model); override with OPENROUTER_TEXT_MODEL in .env.
    openrouter_text_model: str = Field(
        "openrouter/free", alias="OPENROUTER_TEXT_MODEL"
    )

    # Retrieval cascade
    retrieval_min_results: int = Field(3, alias="RETRIEVAL_MIN_RESULTS")

    # Structure stage
    structure_max_chars: int = Field(6000, alias="STRUCTURE_MAX_CHARS")

    # Dashboard session auth (signed cookie)
    session_secret: str = Field(
        "dev-insecure-change-me", alias="SESSION_SECRET"
    )

    # ── AWS Infrastructure Settings (Phase 0) ────────────────────────────
    # RDS (Managed PostgreSQL) — takes precedence over DATABASE_URL when set
    rds_host: str = Field("", alias="RDS_HOST")
    rds_port: int = Field(5432, alias="RDS_PORT")
    rds_database: str = Field("doc_pipeline", alias="RDS_DATABASE")
    rds_username: str = Field("pipeline", alias="RDS_USERNAME")
    rds_password: str = Field("", alias="RDS_PASSWORD")
    secrets_manager_arn: str = Field("", alias="SECRETS_MANAGER_ARN")

    # ElastiCache (Redis) — for real-time events + search suggestions
    redis_host: str = Field("", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")

    @property
    def redis_url(self) -> str | None:
        if self.redis_host:
            return f"redis://{self.redis_host}:{self.redis_port}"
        return None

    # OpenRouter (VLM tier)
    openrouter_api_key: str | None = Field(None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        "https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_model: str = Field(
        "google/gemini-2.5-flash", alias="OPENROUTER_MODEL"
    )
    openrouter_text_model: str = Field(
        "openrouter/free", alias="OPENROUTER_TEXT_MODEL"
    )

    # ── Phase 4 "Make It Smart" feature flags (default OFF — opt-in) ──
    self_healing_enabled: bool = Field(False, alias="SELF_HEALING_ENABLED")
    cost_router_v2_enabled: bool = Field(False, alias="COST_ROUTER_V2_ENABLED")
    monitor_enabled: bool = Field(False, alias="MONITOR_ENABLED")
    aether_llm_enabled: bool = Field(False, alias="AETHER_LLM_ENABLED")
    monitor_interval_seconds: int = Field(30, alias="MONITOR_INTERVAL_SECONDS")

    # Environment
    environment: str = Field("development", alias="ENVIRONMENT")

    # ── Derived property: DATABASE_URL ─────────────────────────────────────
    @property
    def database_url(self) -> str:
        # If RDS_HOST is set, use RDS. Otherwise, fall back to local DATABASE_URL.
        if self.rds_host:
            password = self.rds_password
            if not password and self.secrets_manager_arn:
                password = self._load_secret_value("RDS_PASSWORD")
            return (
                f"postgresql+asyncpg://{self.rds_username}:{password}"
                f"@{self.rds_host}:{self.rds_port}/{self.rds_database}"
            )
        return os.environ.get("DATABASE_URL", "postgresql+asyncpg://pipeline:pipeline@localhost:5432/doc_pipeline")

    def _load_secret_value(self, key: str) -> str:
        """Fetch a key from AWS Secrets Manager (used in Lambda/ECS)."""
        import json as _json
        import boto3
        try:
            client = boto3.client("secretsmanager", region_name=self.aws_region)
            response = client.get_secret_value(SecretId=self.secrets_manager_arn)
            secrets = _json.loads(response["SecretString"])
            return secrets.get(key, "")
        except Exception:
            return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
