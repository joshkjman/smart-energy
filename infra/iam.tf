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

data "aws_iam_policy_document" "weather_ingest_permissions" {
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
    resources = ["${aws_cloudwatch_log_group.weather_ingest.arn}:*"]
  }
}

resource "aws_iam_role" "weather_ingest" {
  name               = "${local.weather_ingest_function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy" "weather_ingest" {
  name   = "weather_ingest_policy"
  role   = aws_iam_role.weather_ingest.id
  policy = data.aws_iam_policy_document.weather_ingest_permissions.json
}