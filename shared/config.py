"""Shared configuration loaded from environment variables."""
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
    s3_access_key: str = Field(..., alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(..., alias="S3_SECRET_KEY")
    s3_bucket: str = Field(..., alias="S3_BUCKET")
    s3_region: str = Field("us-east-1", alias="S3_REGION")

    # Qdrant
    qdrant_url: str = Field(..., alias="QDRANT_URL")
    qdrant_collection: str = Field("document_pages", alias="QDRANT_COLLECTION")

    # Neo4j
    neo4j_uri: str = Field(..., alias="NEO4J_URI")
    neo4j_user: str = Field(..., alias="NEO4J_USER")
    neo4j_password: str = Field(..., alias="NEO4J_PASSWORD")

    # OCR
    ocr_confidence_threshold: int = Field(70, alias="OCR_CONFIDENCE_THRESHOLD")

    # Logging
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_format: str = Field("json", alias="LOG_FORMAT")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
