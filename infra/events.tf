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



resource "aws_cloudwatch_event_rule" "dbt_build" {
  name                = "dbt_build_event"
  description         = "Run dbt build after the day's weather forecast has landed"
  schedule_expression = "cron(15 22 * * ? *)"
}
# late enough that demand through 20:00 is ingested (23 of 24 target hours servable), early enough that a slow run can't cross midnight and lose issue_ts = current_date

resource "aws_cloudwatch_event_target" "dbt_build" {
  rule      = aws_cloudwatch_event_rule.dbt_build.name
  target_id = "dbt_build_codebuild"
  arn       = aws_codebuild_project.dbt.arn
  role_arn  = aws_iam_role.events_dbt_build.arn
}



resource "aws_cloudwatch_event_rule" "inference_lambda" {
  name                = "inference_lambda_event"
  description         = "Invoke lambda for inference predictions"
  schedule_expression = "cron(45 22 * * ? *)"
}
# 30 minutes after the dbt build, so the mart's demand lags are fresh.
# Both are late enough for a 23-hour horizon and early enough not to cross midnight.

resource "aws_cloudwatch_event_target" "inference_lambda" {
  rule      = aws_cloudwatch_event_rule.inference_lambda.name
  target_id = "inference_lambda_event_target"
  arn       = aws_lambda_function.inference_lambda_function.arn
}

resource "aws_lambda_permission" "inference_lambda" {
  statement_id  = "AllowExecutionFromEvents"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.inference_lambda_function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.inference_lambda.arn
}