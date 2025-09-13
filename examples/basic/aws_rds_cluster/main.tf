# Terraform example for AWS RDS Aurora Cluster
# This will create a simple Aurora MySQL cluster

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Configure the AWS Provider
provider "aws" {
  region = "us-west-2"
}

# Create a DB subnet group
resource "aws_db_subnet_group" "aurora_subnet_group" {
  name       = "aurora-subnet-group"
  subnet_ids = ["subnet-12345", "subnet-67890"]

  tags = {
    Name = "Aurora DB subnet group"
  }
}

# Create the Aurora cluster
resource "aws_rds_cluster" "aurora_cluster" {
  cluster_identifier      = "aurora-cluster-demo"
  engine                  = "aurora-mysql"
  engine_version          = "8.0.mysql_aurora.3.05.2"
  database_name           = "testdb"
  master_username         = "admin"
  master_password         = "password123"
  backup_retention_period = 5
  preferred_backup_window = "07:00-09:00"
  skip_final_snapshot     = true

  db_subnet_group_name   = aws_db_subnet_group.aurora_subnet_group.name
  vpc_security_group_ids = ["sg-123456"]

  tags = {
    Name        = "Aurora Cluster Demo"
    Environment = "development"
  }
}

# Aurora cluster instances (typically 1+ instances in the cluster)
resource "aws_rds_cluster_instance" "cluster_instances" {
  count              = 2
  identifier         = "aurora-instance-${count.index}"
  cluster_identifier = aws_rds_cluster.aurora_cluster.id
  instance_class     = "db.r6g.large"
  engine             = aws_rds_cluster.aurora_cluster.engine
  engine_version     = aws_rds_cluster.aurora_cluster.engine_version
}
