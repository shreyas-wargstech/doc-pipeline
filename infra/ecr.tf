resource "aws_ecr_repository" "ingest" {
  name                 = "docintel-${var.environment}/ingest"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "ocr" {
  name                 = "docintel-${var.environment}/ocr"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "light" {
  name                 = "docintel-${var.environment}/light"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "persist_index" {
  name                 = "docintel-${var.environment}/persist-index"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

# Keep last 5 images per repo to avoid unbounded storage
resource "aws_ecr_lifecycle_policy" "keep_last_5" {
  for_each   = toset(["ingest", "ocr", "light", "persist-index"])
  repository = "docintel-${var.environment}/${each.key}"

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })

  depends_on = [
    aws_ecr_repository.ingest,
    aws_ecr_repository.ocr,
    aws_ecr_repository.light,
    aws_ecr_repository.persist_index,
  ]
}
