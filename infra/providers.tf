terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }

  backend "s3" {
    # Replace with your actual state bucket (see docs/AWS_SETUP.md §2.1)
    bucket         = "terraform-state-docintel"
    key            = "doc-pipeline/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "terraform-state-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "doc-pipeline"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
