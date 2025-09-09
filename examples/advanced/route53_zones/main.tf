resource "aws_route53_zone" "public_zone" {
  name    = "example.com"
  comment = "Public zone for example.com"

  tags = {
    Name        = "ExampleZone"
    Environment = "production"
  }
}

resource "aws_route53_zone" "private_zone" {
  name    = "internal.example.com"
  comment = "Private zone for internal services"

  vpc {
    vpc_id = aws_vpc.main.id
  }

  tags = {
    Name        = "InternalZone"
    Environment = "production"
  }
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "main-vpc"
  }
}
