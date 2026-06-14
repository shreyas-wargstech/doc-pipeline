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
