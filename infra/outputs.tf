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

output "ecr_registry_id" {
  value = aws_ecr_repository.ingest.registry_id
}
