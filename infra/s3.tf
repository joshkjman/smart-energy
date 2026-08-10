resource "aws_s3_bucket" "smart_energy_bucket" {
  bucket = "smart-energy-lake"
}

resource "aws_s3_bucket_public_access_block" "smart_energy_bucket_public_access_block" {
  bucket = aws_s3_bucket.smart_energy_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "smart_energy_bucket_encryption" {
  bucket = aws_s3_bucket.smart_energy_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "smart_energy_bucket_versioning" {
  bucket = aws_s3_bucket.smart_energy_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "smart_energy_bucket_lifecycle" {
  bucket = aws_s3_bucket.smart_energy_bucket.id

  rule {
    id = "abort-incomplete-uploads"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 3
    }

    status = "Enabled"
  }

  rule {
    id = "expire-noncurrent-versions-bronze"

    filter {
      prefix = "bronze/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    status = "Enabled"
  }

  rule {
    id = "expire-noncurrent-versions-silver"

    filter {
      prefix = "silver/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }

    status = "Enabled"
  }

  rule {
    id = "expire-noncurrent-versions-gold"

    filter {
      prefix = "gold/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }

    status = "Enabled"
  }

  rule {
    id = "expire-versions-athena-results"

    filter {
      prefix = "athena-results/"
    }

    expiration {
      days = 14
    }

    status = "Enabled"
  }
}