locals {
  dbt_build_project_name = "foresight-dbt-build"
}

resource "aws_codebuild_project" "dbt" {
  name         = local.dbt_build_project_name
  service_role = aws_iam_role.dbt_build.arn

  source {
    type     = "S3"
    location = "${aws_s3_object.build_source_layer.bucket}/${aws_s3_object.build_source_layer.key}"
  }
  artifacts { type = "NO_ARTIFACTS" }
  environment {
    type         = "LINUX_CONTAINER"
    compute_type = "BUILD_GENERAL1_SMALL"
    image        = "aws/codebuild/amazonlinux2-x86_64-standard:5.0"
  }
}

resource "aws_cloudwatch_log_group" "dbt_build" {
  name              = "/aws/codebuild/${local.dbt_build_project_name}"
  retention_in_days = 14
}