locals {
  ingest_image      = "${aws_ecr_repository.ingest.repository_url}:${var.ecr_image_tag}"
  ocr_image         = "${aws_ecr_repository.ocr.repository_url}:${var.ecr_image_tag}"
  light_image       = "${aws_ecr_repository.light.repository_url}:${var.ecr_image_tag}"
  persist_idx_image = "${aws_ecr_repository.persist_index.repository_url}:${var.ecr_image_tag}"

  vpc_subnet_ids         = aws_subnet.private[*].id
  vpc_security_group_ids = [aws_security_group.lambda.id]

  base_env = merge(local.lambda_env_vars, {
    SQS_OCR_QUEUE_URL       = aws_sqs_queue.ocr.url
    SQS_STRUCTURE_QUEUE_URL = aws_sqs_queue.structure.url
    SQS_MATCH_QUEUE_URL     = aws_sqs_queue.match.url
    SQS_PERSIST_QUEUE_URL   = aws_sqs_queue.persist.url
    SQS_INDEX_QUEUE_URL     = aws_sqs_queue.index.url
  })
}

# ─── Ingest Lambda ─────────────────────────────────────────────────────────

resource "aws_lambda_function" "ingest" {
  function_name = "docintel-${var.environment}-ingest"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.ingest_image
  timeout       = 300
  memory_size   = 512

  image_config {
    command = ["cloud.ingest.lambda_handler.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_subnet_ids
    security_group_ids = local.vpc_security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "ingest" }
}

# ─── OCR Lambda ────────────────────────────────────────────────────────────

resource "aws_lambda_function" "ocr" {
  function_name = "docintel-${var.environment}-ocr"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.ocr_image
  timeout       = 300
  memory_size   = 3008

  image_config {
    command = ["cloud.ocr.consumer.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_subnet_ids
    security_group_ids = local.vpc_security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "ocr" }
}

# ─── Structure Lambda ──────────────────────────────────────────────────────

resource "aws_lambda_function" "structure" {
  function_name = "docintel-${var.environment}-structure"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.light_image
  timeout       = 300
  memory_size   = 1024

  image_config {
    command = ["cloud.structure.consumer.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_subnet_ids
    security_group_ids = local.vpc_security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "structure" }
}

# ─── Match Lambda ──────────────────────────────────────────────────────────

resource "aws_lambda_function" "match" {
  function_name = "docintel-${var.environment}-match"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.light_image
  timeout       = 60
  memory_size   = 512

  image_config {
    command = ["cloud.match.consumer.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_subnet_ids
    security_group_ids = local.vpc_security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "match" }
}

# ─── Persist Lambda ────────────────────────────────────────────────────────

resource "aws_lambda_function" "persist" {
  function_name = "docintel-${var.environment}-persist"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.persist_idx_image
  timeout       = 300
  memory_size   = 3008

  image_config {
    command = ["cloud.persist.consumer.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_subnet_ids
    security_group_ids = local.vpc_security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "persist" }
}

# ─── Index Lambda ──────────────────────────────────────────────────────────

resource "aws_lambda_function" "index" {
  function_name = "docintel-${var.environment}-index"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.persist_idx_image
  timeout       = 300
  memory_size   = 3008

  image_config {
    command = ["cloud.index.consumer.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_subnet_ids
    security_group_ids = local.vpc_security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "index" }
}

# ─── Sweeper Lambda ────────────────────────────────────────────────────────

resource "aws_lambda_function" "sweeper" {
  function_name = "docintel-${var.environment}-sweeper"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.light_image
  timeout       = 60
  memory_size   = 512

  image_config {
    command = ["cloud.orchestration.sweeper.handler"]
  }

  vpc_config {
    subnet_ids         = local.vpc_subnet_ids
    security_group_ids = local.vpc_security_group_ids
  }

  environment { variables = local.base_env }

  tags = { Stage = "sweeper" }
}

# ─── Event Source Mappings (SQS → Lambda) ─────────────────────────────────
# ReportBatchItemFailures: only failed records are redelivered, not the whole batch.

resource "aws_lambda_event_source_mapping" "ingest" {
  event_source_arn                   = aws_sqs_queue.ingest.arn
  function_name                      = aws_lambda_function.ingest.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "ocr" {
  event_source_arn                   = aws_sqs_queue.ocr.arn
  function_name                      = aws_lambda_function.ocr.arn
  batch_size                         = 5
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "structure" {
  event_source_arn                   = aws_sqs_queue.structure.arn
  function_name                      = aws_lambda_function.structure.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "match" {
  event_source_arn                   = aws_sqs_queue.match.arn
  function_name                      = aws_lambda_function.match.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "persist" {
  event_source_arn                   = aws_sqs_queue.persist.arn
  function_name                      = aws_lambda_function.persist.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "index" {
  event_source_arn                   = aws_sqs_queue.index.arn
  function_name                      = aws_lambda_function.index.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}
