resource "aws_instance" "example" {
  ami           = "ami-12345678"
  instance_type = "t3.micro"

  tags = {
    Name = "HelloWorld"
  }
}
