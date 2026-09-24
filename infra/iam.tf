data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "weather_ingestion_permissions" {
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.smart_energy_bucket.arn}/bronze/weather_forecast/*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "${aws_cloudwatch_log_group.weather_ingest.arn}:*",
    ]
  }
}

data "aws_iam_policy_document" "demand_ingestion_permissions" {
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.smart_energy_bucket.arn}/bronze/demand/*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "${aws_cloudwatch_log_group.demand_ingest.arn}:*",
    ]
  }
}

data "aws_iam_policy_document" "inference_lambda_permissions" {
  statement {
    effect = "Allow"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryResults",
      "athena:GetQueryExecution"
    ]
    resources = ["arn:aws:athena:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:workgroup/foresight_queries"]
  }

  statement {
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetPartitions"
    ]
    resources = [
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/gold",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/gold/*",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/silver",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/silver/*",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/bronze",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/bronze/*"
    ]
  }

  statement {
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.smart_energy_bucket.arn}/models/demand_lgbm/*",
      "${aws_s3_bucket.smart_energy_bucket.arn}/bronze/*",
      "${aws_s3_bucket.smart_energy_bucket.arn}/silver/*"
    ]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["${aws_s3_bucket.smart_energy_bucket.arn}"]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject"
    ]
    resources = [
      "${aws_s3_bucket.smart_energy_bucket.arn}/athena-results/*",
    ]
  }

  statement {
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
    "${aws_s3_bucket.smart_energy_bucket.arn}/gold/forecasts/*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "${aws_cloudwatch_log_group.inference_lambda.arn}:*",
    ]
  }
}

resource "aws_iam_role" "weather_ingest" {
  name               = "${local.weather_ingest_function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role" "demand_ingest" {
  name               = "${local.demand_ingest_function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role" "inference_lambda" {
  name               = "${local.inference_lambda_function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy" "weather_ingest" {
  name   = "weather_ingest_policy"
  role   = aws_iam_role.weather_ingest.id
  policy = data.aws_iam_policy_document.weather_ingestion_permissions.json
}

resource "aws_iam_role_policy" "demand_ingest" {
  name   = "demand_ingest_policy"
  role   = aws_iam_role.demand_ingest.id
  policy = data.aws_iam_policy_document.demand_ingestion_permissions.json
}

resource "aws_iam_role_policy" "inference_lambda" {
  name   = "inference_lambda_policy"
  role   = aws_iam_role.inference_lambda.id
  policy = data.aws_iam_policy_document.inference_lambda_permissions.json
}