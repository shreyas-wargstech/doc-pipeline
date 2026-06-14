# All secrets in Secrets Manager; pulled at plan time into Lambda env vars.
# Rotation deferred.

resource "aws_secretsmanager_secret" "db_url" {
  name                    = "docintel/${var.environment}/database-url"
  recovery_window_in_days = 0

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
# and the graph store is Amazon Neptune, reached in-VPC by endpoint (a TF output,
# not a secret) with IAM auth disabled for dev — the SG is the access boundary.

resource "aws_secretsmanager_secret" "session" {
  name                    = "docintel/${var.environment}/session"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "session" {
  secret_id     = aws_secretsmanager_secret.session.id
  secret_string = jsonencode({ SESSION_SECRET = var.session_secret })
}

# All env vars shared by every Lambda. Stage-specific queue URLs merged in lambda.tf.
locals {
  lambda_env_vars = {
    DATABASE_URL          = jsondecode(aws_secretsmanager_secret_version.db_url.secret_string)["DATABASE_URL"]
    OPENROUTER_API_KEY    = var.openrouter_api_key
    # Vector store = pgvector in the same DATABASE_URL — no QDRANT_URL.
    # Graph store = Neptune (openCypher over Bolt+TLS). GRAPH_BACKEND=neptune
    # makes ensure_constraints() a no-op. IAM auth off → user/pass unused.
    GRAPH_BACKEND         = "neptune"
    NEO4J_URI             = "neo4j+s://${aws_neptune_cluster.graph.endpoint}:8182"
    NEO4J_USER            = "neptune"
    NEO4J_PASSWORD        = "unused"
    S3_BUCKET             = var.s3_bucket_name
    S3_REGION             = var.aws_region
    # S3_ENDPOINT_URL omitted → blank = real AWS S3
    AWS_REGION            = var.aws_region
    # SQS_ENDPOINT_URL omitted → blank = real AWS SQS
    SESSION_SECRET        = var.session_secret
    LOG_FORMAT            = "json"
    LOG_LEVEL             = "INFO"
    OPENROUTER_MODEL      = "google/gemini-2.5-flash"
    OPENROUTER_TEXT_MODEL = "openrouter/free"
    STRUCTURE_MAX_CHARS   = "6000"
    INDEX_KEYWORD_MODE    = "llm_with_tfidf_fallback"
    RETRIEVAL_MIN_RESULTS = "3"
  }

  ocr_queue_url       = aws_sqs_queue.ocr.url
  structure_queue_url = aws_sqs_queue.structure.url
  match_queue_url     = aws_sqs_queue.match.url
  persist_queue_url   = aws_sqs_queue.persist.url
  index_queue_url     = aws_sqs_queue.index.url
}
