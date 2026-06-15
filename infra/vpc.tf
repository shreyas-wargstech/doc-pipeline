locals {
  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "docintel-${var.environment}" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "docintel-${var.environment}-igw" }
}

resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.public_subnets[count.index]
  availability_zone = local.azs[count.index]

  tags = { Name = "docintel-${var.environment}-public-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "docintel-${var.environment}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count  = 1
  domain = "vpc"
  tags   = { Name = "docintel-${var.environment}-nat-eip-${count.index + 1}" }
}

# Single NAT gateway (dev) — both private subnets route through it
resource "aws_nat_gateway" "main" {
  count         = 1
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags       = { Name = "docintel-${var.environment}-nat-${count.index + 1}" }
  depends_on = [aws_internet_gateway.main]
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.private_subnets[count.index]
  availability_zone = local.azs[count.index]

  tags = { Name = "docintel-${var.environment}-private-${count.index + 1}" }
}

resource "aws_route_table" "private" {
  count  = 2
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[0].id
  }
  tags = { Name = "docintel-${var.environment}-private-rt-${count.index + 1}" }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# Security group: Lambda functions
resource "aws_security_group" "lambda" {
  name        = "docintel-${var.environment}-lambda"
  description = "Lambda functions outbound to RDS, Neptune, internet (NAT)"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound (NAT for OpenRouter; RDS/Neptune via SG rules)"
  }

  tags = { Name = "docintel-${var.environment}-lambda-sg" }
}

# Security group: RDS — only reachable from Lambda SG on 5432
resource "aws_security_group" "rds" {
  name        = "docintel-${var.environment}-rds"
  description = "RDS PostgreSQL - only reachable from Lambda SG"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
    description     = "PostgreSQL from Lambda functions"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "docintel-${var.environment}-rds-sg" }
}

# Security group: Neptune — only reachable from Lambda SG on 8182 (Bolt + openCypher)
resource "aws_security_group" "neptune" {
  name        = "docintel-${var.environment}-neptune"
  description = "Neptune - only reachable from Lambda SG on Bolt/openCypher port"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 8182
    to_port         = 8182
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
    description     = "Neptune (Bolt + openCypher) from Lambda functions"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "docintel-${var.environment}-neptune-sg" }
}
