# Amazon Neptune Serverless — graph store (openCypher).
# All MERGE-on-natural-key Cypher queries port directly from Neo4j.
# Neptune auto-indexes every property and rejects CREATE CONSTRAINT/CREATE INDEX DDL;
# ensure_constraints() is a no-op when GRAPH_BACKEND=neptune (shared/neo4j_client.py).
# IAM auth is disabled for dev — the Lambda SG → Neptune SG rule is the access boundary.

resource "aws_neptune_subnet_group" "graph" {
  name       = "docintel-${var.environment}-neptune"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "docintel-${var.environment}-neptune-subnet-group" }
}

resource "aws_neptune_cluster_parameter_group" "graph" {
  family      = "neptune1.3"
  name        = "docintel-${var.environment}-neptune-params"
  description = "Neptune cluster parameters for docintel"

  parameter {
    name  = "neptune_enable_audit_log"
    value = "0"
  }

  tags = { Name = "docintel-${var.environment}-neptune-params" }
}

resource "aws_neptune_cluster" "graph" {
  cluster_identifier = "docintel-${var.environment}"
  engine             = "neptune"
  engine_version     = "1.3.1.0"

  neptune_subnet_group_name            = aws_neptune_subnet_group.graph.name
  vpc_security_group_ids               = [aws_security_group.neptune.id]
  neptune_cluster_parameter_group_name = aws_neptune_cluster_parameter_group.graph.name

  # IAM auth off for dev — SG is the access boundary.
  # Set iam_database_authentication_enabled=true before prod.
  iam_database_authentication_enabled = false

  # Serverless: cluster scales between neptune_min_ncu and neptune_max_ncu
  serverless_v2_scaling_configuration {
    min_capacity = var.neptune_min_ncu
    max_capacity = var.neptune_max_ncu
  }

  backup_retention_period   = 7
  preferred_backup_window   = "03:00-04:00"
  skip_final_snapshot       = true # set false before prod
  deletion_protection       = false # set true before prod

  apply_immediately = true

  tags = { Name = "docintel-${var.environment}-neptune" }
}

# One Serverless instance in the cluster
resource "aws_neptune_cluster_instance" "graph" {
  count              = 1
  identifier         = "docintel-${var.environment}-neptune-${count.index}"
  cluster_identifier = aws_neptune_cluster.graph.id
  instance_class     = var.neptune_instance_class # "db.serverless"
  engine             = "neptune"
  engine_version     = "1.3.1.0"

  neptune_subnet_group_name            = aws_neptune_subnet_group.graph.name
  neptune_parameter_group_name         = "default.neptune1.3"
  apply_immediately                    = true

  tags = { Name = "docintel-${var.environment}-neptune-instance" }
}
