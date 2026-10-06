resource "aws_cloudwatch_event_rule" "weather_ingest" {
  name                = "weather_ingest_event"
  description         = "Invoke lambda for weather ingestion from API"
  schedule_expression = "cron(0 5 * * ? *)"
}

resource "aws_cloudwatch_event_target" "weather_ingest" {
  rule      = aws_cloudwatch_event_rule.weather_ingest.name
  target_id = "weather_ingest_event_target"
  arn       = aws_lambda_function.weather_ingest_lambda_function.arn
}

resource "aws_lambda_permission" "weather_ingest" {
  statement_id  = "AllowExecutionFromEvents"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.weather_ingest_lambda_function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weather_ingest.arn
}



resource "aws_cloudwatch_event_rule" "demand_ingest" {
  name                = "demand_ingest_event"
  description         = "Invoke lambda for demand ingestion from API"
  schedule_expression = "cron(5 * * * ? *)"
}

resource "aws_cloudwatch_event_target" "demand_ingest" {
  rule      = aws_cloudwatch_event_rule.demand_ingest.name
  target_id = "demand_ingest_event_target"
  arn       = aws_lambda_function.demand_ingest_lambda_function.arn
}

resource "aws_lambda_permission" "demand_ingest" {
  statement_id  = "AllowExecutionFromEvents"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.demand_ingest_lambda_function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.demand_ingest.arn
}



resource "aws_cloudwatch_event_rule" "sfn_state_machine" {
  name                = "sfn_state_machine_event"
  description         = "Run state machine start after hourly demand ingestion"
  schedule_expression = "cron(10 22 * * ? *)"
}

resource "aws_cloudwatch_event_target" "sfn_state_machine" {
  rule      = aws_cloudwatch_event_rule.sfn_state_machine.name
  target_id = "sfn_state_machine"
  arn       = aws_sfn_state_machine.nightly.arn
  role_arn  = aws_iam_role.events_start_state.arn
}