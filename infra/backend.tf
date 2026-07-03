terraform {
    required_providers {
        aws = {
            source = "hashicorp/aws"
            version = "~> 5.92"
        }
    }
    required_version = ">= 1.10"

    backend "s3" {
        bucket = "smart-energy-tfstate"
        key = "global/s3/terraform.tfstate"
        region = "eu-west-2"
        encrypt = true
        use_lockfile = true
    }
}