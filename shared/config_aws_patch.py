"""Add AWS-specific settings to the existing pydantic-settings config.

This is a PATCH to the existing shared/config.py. Apply the following changes
after the existing configuration to extend it with AWS settings.

The existing config uses pydantic-settings with environment variables.
These AWS settings follow the same pattern.
"""

# To apply this patch to shared/config.py, add the following fields to the Settings class:

AWS_SETTINGS_PATCH = """
    # ── AWS Region & Credentials ───────────────────────────────────────────
    aws_region: str = "ap-south-1"  # Mumbai region for India
    aws_access_key_id: str = ""  # Only for local dev; Lambda/ECS use IAM role
    aws_secret_access_key: str = ""  # Only for local dev
    
    # ── S3 ────────────────────────────────────────────────────────────────
    s3_bucket: str = "docintel-documents"  # Document storage bucket name
    s3_region: str = "ap-south-1"
    
    # ── SQS ───────────────────────────────────────────────────────────────
    sqs_ocr_queue_url: str = ""  # OCR queue (page-level, FIFO)
    sqs_structure_queue_url: str = ""  # Structure queue (document-level, FIFO)
    sqs_match_queue_url: str = ""  # Match queue (document-level, FIFO)
    sqs_persist_queue_url: str = ""  # Persist queue (document-level, FIFO)
    sqs_index_queue_url: str = ""  # Index queue (document-level, FIFO)
    
    # ── RDS (Managed PostgreSQL) ───────────────────────────────────────────
    rds_host: str = ""  # RDS endpoint (e.g., docintel-postgres.abc.ap-south-1.rds.amazonaws.com)
    rds_port: int = 5432
    rds_database: str = "doc_pipeline"
    rds_username: str = "pipeline"
    rds_password: str = ""  # Fetched from Secrets Manager in production
    
    # ── ElastiCache (Redis) ───────────────────────────────────────────────
    redis_host: str = ""  # Redis endpoint (e.g., docintel-redis.abc.cache.amazonaws.com)
    redis_port: int = 6379
    
    # ── Secrets Manager ───────────────────────────────────────────────────
    secrets_manager_arn: str = ""  # ARN of the secret containing all credentials
    
    # ── External Managed Services ────────────────────────────────────────
    qdrant_url: str = ""  # Qdrant Cloud URL (e.g., https://xyz.cloud.qdrant.io:6333)
    qdrant_api_key: str = ""  # Qdrant Cloud API key (from Secrets Manager in production)
    
    neo4j_uri: str = ""  # Neo4j Aura URI (e.g., bolt+s://xyz.databases.neo4j.io)
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""  # From Secrets Manager in production
    
    # ── OpenRouter (VLM tier) ────────────────────────────────────────────
    openrouter_api_key: str = ""  # From Secrets Manager in production
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "google/gemini-2.5-flash"
    
    # ── Lambda-specific ───────────────────────────────────────────────────
    lambda_memory_size: int = 1024  # MB (used for capacity planning, not runtime config)
    lambda_timeout: int = 60  # seconds (used for capacity planning)
    
    # ── ECS Fargate API ───────────────────────────────────────────────────
    ecs_api_cpu: int = 512  # 256 = 0.25 vCPU, 512 = 0.5 vCPU
    ecs_api_memory: int = 1024  # MB
    ecs_api_task_count: int = 1  # Number of tasks
    
    # ── Environment ──────────────────────────────────────────────────────
    environment: str = "development"  # development | staging | production
    
    # ── Derived property: DATABASE_URL for asyncpg ──────────────────────
    @property
    def database_url(self) -> str:
        # If RDS_HOST is set, use RDS. Otherwise, fall back to local DATABASE_URL.
        if self.rds_host:
            password = self.rds_password or self._get_secret_value("RDS_PASSWORD")
            return f"postgresql+asyncpg://{self.rds_username}:{password}@{self.rds_host}:{self.rds_port}/{self.rds_database}"
        # Return existing local DATABASE_URL if no RDS config
        return os.environ.get("DATABASE_URL", "postgresql+asyncpg://pipeline:pipeline@localhost:5432/doc_pipeline")
    
    def _get_secret_value(self, key: str) -> str:
        # Fetch from AWS Secrets Manager if ARN is set
        if self.secrets_manager_arn:
            try:
                import boto3
                client = boto3.client("secretsmanager", region_name=self.aws_region)
                response = client.get_secret_value(SecretId=self.secrets_manager_arn)
                import json
                secrets = json.loads(response["SecretString"])
                return secrets.get(key, "")
            except Exception:
                pass
        return ""
"""

# Instructions for applying this patch:
# 1. Open shared/config.py
# 2. Find the Settings class (pydantic-settings BaseSettings)
# 3. Add all the fields above after the existing fields
# 4. Ensure the `database_url` property does not conflict with the existing field
# 5. If there is already a `database_url` field, rename it to `_database_url` or modify it to use the property approach above

# Note: In Lambda/ECS, credentials are resolved via IAM role, not env vars.
# The `aws_access_key_id` and `aws_secret_access_key` are only used for local development.
# In production, boto3 automatically uses the IAM role attached to the Lambda/ECS task.
