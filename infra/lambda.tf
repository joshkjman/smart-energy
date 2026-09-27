data "archive_file" "layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../build/layer"
  output_path = "${path.module}/../build/layer.zip"
  excludes = [
    "**/__pycache__/**",
    "**/tests/**",
    "python/bin/**",
  ]
}

resource "aws_lambda_layer_version" "ingest_lambda_layer" {
  filename   = data.archive_file.layer_zip.output_path
  layer_name = "ingest_lambda_layer"

  source_code_hash         = data.archive_file.layer_zip.output_base64sha256
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["x86_64"]
}

data "archive_file" "inference_layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../build/inference_layer"
  output_path = "${path.module}/../build/inference_layer.zip"
  excludes = [
    "**/__pycache__/**",
    "**/tests/**",
    "python/bin/**",
  ]
}

resource "aws_lambda_layer_version" "inference_lambda_layer" {
  s3_bucket  = aws_s3_object.inference_layer.bucket
  s3_key     = aws_s3_object.inference_layer.key
  layer_name = "inference_lambda_layer"

  source_code_hash         = data.archive_file.inference_layer_zip.output_base64sha256
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["x86_64"]
}

data "archive_file" "dbt_layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../build/dbt_layer"
  output_path = "${path.module}/../build/dbt_layer.zip"
  excludes = [
    "**/__pycache__/**",
    "target/**",
    "logs/**"
  ]
}

resource "aws_lambda_layer_version" "dbt_lambda_layer" {
  filename   = data.archive_file.dbt_layer_zip.output_path
  layer_name = "dbt_lambda_layer"

  source_code_hash         = data.archive_file.dbt_layer_zip.output_base64sha256
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["x86_64"]
}

data "archive_file" "code_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/../build/code.zip"
  excludes    = ["ml/**", "**/__pycache__/**"]
}

data "archive_file" "dbt_code_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../dbt"
  output_path = "${path.module}/../build/dbt_code.zip"
  excludes = [
    "**/__pycache__/**",
    "target/**",
    "logs/**"
  ]
}

locals {
  weather_ingest_function_name = "weather_ingest_lambda"
}

resource "aws_cloudwatch_log_group" "weather_ingest" {
  name              = "/aws/lambda/${local.weather_ingest_function_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "weather_ingest_lambda_function" {
  filename      = data.archive_file.code_zip.output_path
  function_name = local.weather_ingest_function_name
  role          = aws_iam_role.weather_ingest.arn
  handler       = "ingestion.weather_forecast_ingest.handler"
  runtime       = "python3.12"

  architectures = ["x86_64"]

  layers = [aws_lambda_layer_version.ingest_lambda_layer.arn]

  timeout          = 60
  memory_size      = 512
  depends_on       = [aws_cloudwatch_log_group.weather_ingest]
  source_code_hash = data.archive_file.code_zip.output_base64sha256

  environment {
    variables = {
      BRONZE_BUCKET = aws_s3_bucket.smart_energy_bucket.bucket
    }
  }
}



locals {
  demand_ingest_function_name = "demand_ingest_lambda"
}

resource "aws_cloudwatch_log_group" "demand_ingest" {
  name              = "/aws/lambda/${local.demand_ingest_function_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "demand_ingest_lambda_function" {
  filename      = data.archive_file.code_zip.output_path
  function_name = local.demand_ingest_function_name
  role          = aws_iam_role.demand_ingest.arn
  handler       = "ingestion.demand_ingest.handler"
  runtime       = "python3.12"

  architectures = ["x86_64"]

  layers = [aws_lambda_layer_version.ingest_lambda_layer.arn]

  timeout          = 60
  memory_size      = 256
  depends_on       = [aws_cloudwatch_log_group.demand_ingest]
  source_code_hash = data.archive_file.code_zip.output_base64sha256

  environment {
    variables = {
      BRONZE_BUCKET = aws_s3_bucket.smart_energy_bucket.bucket
    }
  }
}



locals {
  inference_lambda_function_name = "inference_lambda"
}

resource "aws_cloudwatch_log_group" "inference_lambda" {
  name              = "/aws/lambda/${local.inference_lambda_function_name}"
  retention_in_days = 14
}



locals {
  dbt_lambda_function_name = "dbt_lambda"
}

resource "aws_cloudwatch_log_group" "dbt_lambda" {
  name              = "/aws/lambda/${local.dbt_lambda_function_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "dbt_lambda_function" {
  filename      = data.archive_file.dbt_code_zip.output_path
  function_name = local.dbt_lambda_function_name
  role          = aws_iam_role.dbt_lambda.arn
  handler       = "lambda_handler.handler"
  runtime       = "python3.12"

  architectures = ["x86_64"]

  layers = [aws_lambda_layer_version.dbt_lambda_layer.arn]

  timeout          = 300
  memory_size      = 1024
  depends_on       = [aws_cloudwatch_log_group.dbt_lambda]
  source_code_hash = data.archive_file.dbt_code_zip.output_base64sha256

  environment {
    variables = {
      DBT_TARGET_PATH = "/tmp/target"
      DBT_LOG_PATH    = "/tmp/logs"
    }
  }
}