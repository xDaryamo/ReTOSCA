provider "aws" {
  region = "eu-west-1"
}





resource "aws_vpc" "main" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "rds-demo-vpc" }
}

resource "aws_subnet" "private_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.1.0/24"
  availability_zone       = "eu-west-1a"
  map_public_ip_on_launch = false

  tags = { Name = "rds-demo-private-a" }
}

resource "aws_subnet" "private_b" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.2.0/24"
  availability_zone       = "eu-west-1b"
  map_public_ip_on_launch = false

  tags = { Name = "rds-demo-private-b" }
}


resource "aws_security_group" "db_sg" {
  name        = "rds-demo-db-sg"
  description = "Allow MySQL from VPC CIDR"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "rds-demo-db-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "mysql_in" {
  security_group_id = aws_security_group.db_sg.id
  cidr_ipv4         = aws_vpc.main.cidr_block
  ip_protocol       = "tcp"
  from_port         = 3306
  to_port           = 3306
}

resource "aws_vpc_security_group_egress_rule" "all_out" {
  security_group_id = aws_security_group.db_sg.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}


resource "aws_db_subnet_group" "rds_subnets" {
  name       = "rds-demo-subnet-group"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  tags = { Name = "rds-demo-subnet-group" }
}




resource "aws_db_instance" "mysql" {
  identifier                 = "rds-demo-mysql"
  engine                     = "mysql"
  engine_version             = "8.0"
  instance_class             = "db.t3.micro"
  allocated_storage          = 20
  storage_type               = "gp3"
  username                   = "admin"
  password                   = "changeme123!"
  db_subnet_group_name       = aws_db_subnet_group.rds_subnets.name
  vpc_security_group_ids     = [aws_security_group.db_sg.id]
  publicly_accessible        = false
  multi_az                   = false
  skip_final_snapshot        = true
  deletion_protection        = false


  port                       = 3306

  tags = { Name = "rds-demo-mysql" }
}
