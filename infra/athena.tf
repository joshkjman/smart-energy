resource "aws_athena_workgroup" "foresight_queries" {
  name = "foresight_queries"

  force_destroy = true
  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 104857600

    result_configuration {
      output_location = "s3://smart-energy-lake/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}