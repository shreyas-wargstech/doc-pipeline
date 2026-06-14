resource "aws_sns_topic" "alerts" {
  name = "docintel-${var.environment}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  dlqs = {
    ingest    = aws_sqs_queue.ingest_dlq.name
    ocr       = aws_sqs_queue.ocr_dlq.name
    structure = aws_sqs_queue.structure_dlq.name
    match     = aws_sqs_queue.match_dlq.name
    persist   = aws_sqs_queue.persist_dlq.name
    index     = aws_sqs_queue.index_dlq.name
  }

  lambda_names = {
    ingest    = aws_lambda_function.ingest.function_name
    ocr       = aws_lambda_function.ocr.function_name
    structure = aws_lambda_function.structure.function_name
    match     = aws_lambda_function.match.function_name
    persist   = aws_lambda_function.persist.function_name
    index     = aws_lambda_function.index.function_name
    sweeper   = aws_lambda_function.sweeper.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  for_each = local.dlqs

  alarm_name          = "docintel-${var.environment}-${each.key}-dlq-nonempty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "DLQ ${each.value} has messages — document failed 3 retries"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = each.value
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.lambda_names

  alarm_name          = "docintel-${var.environment}-${each.key}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Lambda ${each.value} has >5 errors in 5 min"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = each.value
  }
}
