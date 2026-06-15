resource "aws_db_subnet_group" "postgres" {
  name       = "docintel-${var.environment}-postgres"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "docintel-${var.environment}-db-subnet-group" }
}

resource "aws_db_parameter_group" "postgres16" {
  name   = "docintel-${var.environment}-pg16"
  family = "postgres16"

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  tags = { Name = "docintel-${var.environment}-pg16-params" }
}

resource "aws_db_instance" "postgres" {
  identifier = "docintel-${var.environment}"

  engine         = "postgres"
  engine_version = "16.9"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "doc_pipeline"
  username = "pipeline"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.postgres16.name

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  deletion_protection = false # set true before prod
  skip_final_snapshot = true  # set false before prod

  tags = { Name = "docintel-${var.environment}-postgres" }
}
