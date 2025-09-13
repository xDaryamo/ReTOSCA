variable "vpc_cidr" {
    description = "The CIDR block for the VPC."
    type        = string
    default     = "10.0.1.0/24"
}

variable "name" {
    description = "The name of the resource."
    type        = string
    default     = "main"
}
