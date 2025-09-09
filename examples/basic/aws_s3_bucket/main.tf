resource "aws_s3_bucket" "example" {
  bucket = "tosca-reverse-engineering-test-bucket-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "My bucket"
    Environment = "Dev"
  }
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}
