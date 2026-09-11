locals {
  weather_ingest_function_name = "weather_ingest_lambda"
}

resource "aws_cloudwatch_log_group" "weather_ingest" {
  name              = "/aws/lambda/${local.weather_ingest_function_name}"
  retention_in_days = 14
}

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

data "archive_file" "code_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/../build/code.zip"
  excludes    = ["ml/**", "**/__pycache__/**"]
}

resource "aws_lambda_layer_version" "ingest_lambda_layer" {
  filename   = data.archive_file.layer_zip.output_path
  layer_name = "ingest_lambda_layer"

  source_code_hash         = data.archive_file.layer_zip.output_base64sha256
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["x86_64"]
}

