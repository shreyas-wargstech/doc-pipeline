resource "aws_cloudwatch_event_rule" "sweeper" {
  name                = "docintel-${var.environment}-sweeper"
  description         = "Fan-in: advance OCR-complete documents to Structure queue"
  schedule_expression = "rate(2 minutes)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "sweeper_lambda" {
  rule      = aws_cloudwatch_event_rule.sweeper.name
  target_id = "SweepLambda"
  arn       = aws_lambda_function.sweeper.arn
}

resource "aws_lambda_permission" "eventbridge_sweeper" {
  statement_id  = "AllowEventBridgeSweeper"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sweeper.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sweeper.arn
}
