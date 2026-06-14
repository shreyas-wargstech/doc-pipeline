resource "aws_s3_bucket" "documents" {
  bucket = var.s3_bucket_name

  tags = { Name = "docintel-${var.environment}-documents" }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Only manifest.json uploads trigger the ingest Lambda
resource "aws_s3_bucket_notification" "manifest_created" {
  bucket = aws_s3_bucket.documents.id

  queue {
    id            = "manifest-created"
    queue_arn     = aws_sqs_queue.ingest.arn
    events        = ["s3:ObjectCreated:*"]
    filter_suffix = "/manifest.json"
  }

  depends_on = [aws_sqs_queue_policy.ingest_s3]
}
