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

data "aws_iam_policy_document" "events_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "codebuild_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
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
      "athena:GetQueryExecution",
      "athena:GetWorkGroup",
      "athena:GetDataCatalog"
    ]
    resources = ["arn:aws:athena:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:workgroup/foresight_queries"]
  }

  statement {
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetPartitions",
      "glue:GetTables"
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
  statement {
    effect    = "Allow"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.smart_energy_bucket.arn]
  }
}

data "aws_iam_policy_document" "dbt_build_permissions" {
  statement {
    effect = "Allow"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryResults",
      "athena:GetQueryExecution",
      "athena:GetWorkGroup",
      "athena:GetDataCatalog",
      "athena:StopQueryExectution"
    ]
    resources = ["arn:aws:athena:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:workgroup/foresight_queries"]
  }

  statement {
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetPartitions",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:GetDatabases",
      "glue:GetTables",
      "glue:GetTableVersions",
      "glue:DeleteTableVersion",
      "glue:BatchDeleteTableVersion",
      "glue:BatchDeleteTable"
    ]
    resources = [
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/gold",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/gold/*",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/silver",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/silver/*",
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetPartitions",
      "glue:GetDatabases",
      "glue:GetTables"
    ]
    resources = [
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/bronze",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/bronze/*",
    ]
  }

  statement {
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.smart_energy_bucket.arn}/bronze/*",
      "${aws_s3_bucket.smart_energy_bucket.arn}/silver/*",
      "${aws_s3_bucket.smart_energy_bucket.arn}/build-source/*"
    ]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["${aws_s3_bucket.smart_energy_bucket.arn}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["bronze/*", "silver/*", "gold/*", "athena-results/*"]
    }
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject"
    ]
    resources = [
      "${aws_s3_bucket.smart_energy_bucket.arn}/athena-results/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucketMultipartUploads",
      "s3:ListMultipartUploadParts",
      "s3:AbortMultipartUpload"
    ]
    resources = [
      "${aws_s3_bucket.smart_energy_bucket.arn}/silver/*",
      "${aws_s3_bucket.smart_energy_bucket.arn}/gold/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "${aws_cloudwatch_log_group.dbt_build.arn}:*",
    ]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.smart_energy_bucket.arn]
  }
}

data "aws_iam_policy_document" "events_start_build" {
  statement {
    effect    = "Allow"
    actions   = ["codebuild:StartBuild"]
    resources = [aws_codebuild_project.dbt.arn]
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

resource "aws_iam_role" "dbt_build" {
  name               = "foresight-dbt-build-role"
  assume_role_policy = data.aws_iam_policy_document.codebuild_trust.json
}

resource "aws_iam_role" "events_dbt_build" {
  name               = "events-dbt-build-role"
  assume_role_policy = data.aws_iam_policy_document.events_trust.json
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

resource "aws_iam_role_policy" "dbt_build" {
  name   = "dbt_build_policy"
  role   = aws_iam_role.dbt_build.id
  policy = data.aws_iam_policy_document.dbt_build_permissions.json
}

resource "aws_iam_role_policy" "events_dbt_build" {
  name   = "events_dbt_build_policy"
  role   = aws_iam_role.events_dbt_build.id
  policy = data.aws_iam_policy_document.events_start_build.json
}