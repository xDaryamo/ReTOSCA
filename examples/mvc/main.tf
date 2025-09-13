

############################
# Networking (VPC & Subnet)
############################

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "mvc-vpc" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "mvc-igw" }
}

# Due AZ “logiche” per semplicità
resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "us-east-1a"
  tags = { Name = "public-a" }
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.2.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "us-east-1b"
  tags = { Name = "public-b" }
}

resource "aws_subnet" "private_db_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.10.0/24"
  availability_zone = "us-east-1a"
  tags = { Name = "private-db-a" }
}

resource "aws_subnet" "private_db_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "us-east-1b"
  tags = { Name = "private-db-b" }
}

# Route: public → Internet
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "public-rt" }
}
resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}
resource "aws_route_table_association" "assoc_pub_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}
resource "aws_route_table_association" "assoc_pub_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

#########################
# Security Groups (FW)
#########################

# ALB: HTTP 80 pubblico
resource "aws_security_group" "alb_sg" {
  name        = "alb-sg"
  description = "Allow HTTP"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "alb-sg" }
}

resource "aws_security_group" "app_sg" {
  name        = "app-sg"
  description = "App from ALB"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "app-sg" }
}

resource "aws_security_group" "db_sg" {
  name   = "db-sg"
  vpc_id = aws_vpc.main.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app_sg.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "db-sg" }
}

resource "aws_security_group" "redis_sg" {
  name   = "redis-sg"
  vpc_id = aws_vpc.main.id
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app_sg.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "redis-sg" }
}

############################
# S3 per backup/artefatti
############################

resource "aws_s3_bucket" "backups" {
  bucket = "mvc-app-backups-localstack"
  force_destroy = true
  tags = { Name = "app-backups" }
}

resource "aws_s3_bucket_versioning" "backups_versioning" {
  bucket = aws_s3_bucket.backups.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups_lifecycle" {
  bucket = aws_s3_bucket.backups.id
  rule {
    id     = "expire-old"
    status = "Enabled"
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

############################
# Application Load Balancer
############################

resource "aws_lb" "app_alb" {
  name               = "mvc-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]
  tags = { Name = "mvc-alb" }
}

resource "aws_lb_target_group" "app_tg" {
  name        = "mvc-tg"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"
  health_check {
    path = "/"
    port = "8080"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app_alb.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app_tg.arn
  }
}

############################
# EC2 x2 (mock in LocalStack)
############################


locals {
  dummy_ami = "ami-12345678"
}

resource "aws_instance" "app_a" {
  ami                         = local.dummy_ami
  instance_type               = "t3.micro"
  subnet_id                   = aws_subnet.public_a.id
  vpc_security_group_ids      = [aws_security_group.app_sg.id]
  associate_public_ip_address = true
  user_data                   = <<-EOT
              #!/bin/bash
              # Demo HTTP su 8080: serve “Hello MVC”
              nohup sh -c 'while true; do echo -e "HTTP/1.1 200 OK\n\nHello MVC (A)" | nc -l -p 8080 -q 1; done' &
            EOT
  tags = { Name = "app-a" }
}

resource "aws_instance" "app_b" {
  ami                         = local.dummy_ami
  instance_type               = "t3.micro"
  subnet_id                   = aws_subnet.public_b.id
  vpc_security_group_ids      = [aws_security_group.app_sg.id]
  associate_public_ip_address = true
  user_data                   = <<-EOT
              #!/bin/bash
              nohup sh -c 'while true; do echo -e "HTTP/1.1 200 OK\n\nHello MVC (B)" | nc -l -p 8080 -q 1; done' &
            EOT
  tags = { Name = "app-b" }
}

resource "aws_lb_target_group_attachment" "attach_a" {
  target_group_arn = aws_lb_target_group.app_tg.arn
  target_id        = aws_instance.app_a.id
  port             = 8080
}
resource "aws_lb_target_group_attachment" "attach_b" {
  target_group_arn = aws_lb_target_group.app_tg.arn
  target_id        = aws_instance.app_b.id
  port             = 8080
}

############################
# Database (RDS Postgres)
############################

# SUBNET GROUP per DB in subnet private
resource "aws_db_subnet_group" "db_subnets" {
  name       = "db-subnets"
  subnet_ids = [aws_subnet.private_db_a.id, aws_subnet.private_db_b.id]
  tags = { Name = "db-subnet-group" }
}

resource "aws_db_instance" "postgres" {
  identifier              = "mvc-postgres"
  engine                  = "postgres"
  engine_version          = "13.7"
  instance_class          = "db.t3.micro"
  username                = "appuser"
  password                = "appsecret"
  allocated_storage       = 20
  db_subnet_group_name    = aws_db_subnet_group.db_subnets.name
  vpc_security_group_ids  = [aws_security_group.db_sg.id]
  skip_final_snapshot     = true
  publicly_accessible     = false
  deletion_protection     = false
  # LocalStack: accetta valori simulati
  tags = { Name = "mvc-db" }
}

############################
# Cache (ElastiCache Redis)
############################

resource "aws_elasticache_subnet_group" "redis_subnets" {
  name       = "redis-subnets"
  subnet_ids = [aws_subnet.private_db_a.id, aws_subnet.private_db_b.id]
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "mvc-redis"
  engine               = "redis"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis_subnets.name
  security_group_ids   = [aws_security_group.redis_sg.id]
  apply_immediately    = true
  tags = { Name = "mvc-redis" }
}

############################
# DNS (Route53) → ALB
############################

resource "aws_route53_zone" "private" {
  name = "local."
  vpc {
    vpc_id = aws_vpc.main.id
  }
  comment = "Private zone for local resolution"
}

resource "aws_route53_record" "app_dns" {
  zone_id = aws_route53_zone.private.zone_id
  name    = "app.local"
  type    = "A"
  alias {
    name                   = aws_lb.app_alb.dns_name
    zone_id                = aws_lb.app_alb.zone_id
    evaluate_target_health = false
  }
}
