# ─── Ingest queue (standard — required for S3 event notifications) ─────────

resource "aws_sqs_queue" "ingest_dlq" {
  name                      = "docintel-${var.environment}-ingest-dlq"
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "ingest" {
  name                       = "docintel-${var.environment}-ingest"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingest_dlq.arn
    maxReceiveCount     = 3
  })
}

# Allow S3 to send messages to this queue
resource "aws_sqs_queue_policy" "ingest_s3" {
  queue_url = aws_sqs_queue.ingest.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.ingest.arn
      Condition = {
        ArnLike = { "aws:SourceArn" = "arn:aws:s3:::${var.s3_bucket_name}" }
      }
    }]
  })
}

# ─── OCR FIFO queue ────────────────────────────────────────────────────────

resource "aws_sqs_queue" "ocr_dlq" {
  name                      = "docintel-${var.environment}-ocr-dlq.fifo"
  fifo_queue                = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "ocr" {
  name                        = "docintel-${var.environment}-ocr.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 300
  message_retention_seconds   = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ocr_dlq.arn
    maxReceiveCount     = 3
  })
}

# ─── Structure FIFO queue ──────────────────────────────────────────────────

resource "aws_sqs_queue" "structure_dlq" {
  name                      = "docintel-${var.environment}-structure-dlq.fifo"
  fifo_queue                = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "structure" {
  name                        = "docintel-${var.environment}-structure.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 300
  message_retention_seconds   = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.structure_dlq.arn
    maxReceiveCount     = 3
  })
}

# ─── Match FIFO queue ──────────────────────────────────────────────────────

resource "aws_sqs_queue" "match_dlq" {
  name                      = "docintel-${var.environment}-match-dlq.fifo"
  fifo_queue                = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "match" {
  name                        = "docintel-${var.environment}-match.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 60
  message_retention_seconds   = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.match_dlq.arn
    maxReceiveCount     = 3
  })
}

# ─── Persist FIFO queue ────────────────────────────────────────────────────

resource "aws_sqs_queue" "persist_dlq" {
  name                      = "docintel-${var.environment}-persist-dlq.fifo"
  fifo_queue                = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "persist" {
  name                        = "docintel-${var.environment}-persist.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 300
  message_retention_seconds   = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.persist_dlq.arn
    maxReceiveCount     = 3
  })
}

# ─── Index FIFO queue ──────────────────────────────────────────────────────

resource "aws_sqs_queue" "index_dlq" {
  name                      = "docintel-${var.environment}-index-dlq.fifo"
  fifo_queue                = true
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "index" {
  name                        = "docintel-${var.environment}-index.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 300
  message_retention_seconds   = 86400
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.index_dlq.arn
    maxReceiveCount     = 3
  })
}
