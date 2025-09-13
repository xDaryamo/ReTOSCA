#!/bin/bash

# ReTOSCA Runner Script
# Easy-to-use wrapper for running ReTOSCA with Docker Compose

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Detect Docker Compose command
detect_docker_compose() {
    if command -v docker compose &> /dev/null; then
        echo "docker compose"
    elif command -v docker-compose &> /dev/null; then
        echo "docker-compose"
    else
        echo -e "${RED}❌ Neither 'docker compose' nor 'docker-compose' found${NC}" >&2
        echo -e "${YELLOW}💡 Please install Docker Compose${NC}" >&2
        exit 1
    fi
}

# Set the Docker Compose command
DOCKER_COMPOSE=$(detect_docker_compose)

# Default values
COMPOSE_FILE="docker-compose.yml"
TERRAFORM_DIR=""
OUTPUT_DIR="./output"
EXAMPLES_DIR="./examples"
VERBOSE=false
DEBUG=false
VALIDATE=true

# Function to show usage
show_usage() {
    echo -e "${BLUE}ReTOSCA - Reverse Engineer Terraform to TOSCA${NC}"
    echo ""
    echo "Usage: $0 [OPTIONS] <terraform-directory> [output-file]"
    echo ""
    echo "Arguments:"
    echo "  terraform-directory    Directory containing Terraform (.tf) files"
    echo "  output-file           Output TOSCA file (default: output/result.yaml)"
    echo ""
    echo "Options:"
    echo "  -h, --help           Show this help message"
    echo "  -v, --verbose        Enable verbose logging"
    echo "  -d, --debug          Enable debug logging"
    echo "  --no-validate        Skip TOSCA validation"
    echo "  --standalone         Use standalone Docker Compose file"
    echo "  --extract-examples   Extract built-in examples to ./examples"
    echo "  --validate-only      Only validate existing TOSCA files in output directory"
    echo "  --shell              Start interactive shell"
    echo ""
    echo "Examples:"
    echo "  # Basic usage"
    echo "  $0 ./my-terraform-project"
    echo ""
    echo "  # Specify output file"
    echo "  $0 ./my-terraform-project output/my-infrastructure.yaml"
    echo ""
    echo "  # With verbose logging"
    echo "  $0 -v ./my-terraform-project"
    echo ""
    echo "  # Extract examples first"
    echo "  $0 --extract-examples"
    echo ""
    echo "  # Process extracted examples"
    echo "  $0 examples/basic/aws_s3_bucket"
    echo ""
    echo "  # Validate existing TOSCA files"
    echo "  $0 --validate-only"
    echo ""
}

# Function to check prerequisites
check_prerequisites() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker is not installed or not in PATH${NC}" >&2
        exit 1
    fi

    if ! command -v docker compose &> /dev/null && ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}❌ Docker Compose is not installed or not in PATH${NC}" >&2
        exit 1
    fi
}

# Function to extract examples
extract_examples() {
    echo -e "${BLUE}🔄 Extracting built-in examples...${NC}"

    EXAMPLES_DIR="${EXAMPLES_DIR}" $DOCKER_COMPOSE -f "$COMPOSE_FILE" run --rm extract-examples

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Examples extracted to $EXAMPLES_DIR${NC}"
        echo -e "${YELLOW}💡 You can now run: $0 examples/basic/aws_s3_bucket${NC}"
    else
        echo -e "${RED}❌ Failed to extract examples${NC}" >&2
        exit 1
    fi
}

# Function to validate TOSCA files
validate_only() {
    echo -e "${BLUE}🔍 Validating TOSCA files in $OUTPUT_DIR...${NC}"

    if [ ! -d "$OUTPUT_DIR" ]; then
        echo -e "${RED}❌ Output directory $OUTPUT_DIR does not exist${NC}" >&2
        exit 1
    fi

    OUTPUT_DIR="$OUTPUT_DIR" $DOCKER_COMPOSE -f "$COMPOSE_FILE" run --rm validate
}

# Function to start interactive shell
start_shell() {
    echo -e "${BLUE}🐚 Starting interactive shell...${NC}"
    echo -e "${YELLOW}💡 Use 'python -m src.main --help' for ReTOSCA commands${NC}"

    if [ "$COMPOSE_FILE" = "docker-compose-standalone.yml" ]; then
        TERRAFORM_DIR="${TERRAFORM_DIR:-./terraform}" OUTPUT_DIR="$OUTPUT_DIR" $DOCKER_COMPOSE -f "$COMPOSE_FILE" run --rm shell
    else
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" run --rm retosca bash
    fi
}

# Function to run ReTOSCA
run_retosca() {
    local terraform_dir="$1"
    local output_file="$2"

    # Validate terraform directory
    if [ ! -d "$terraform_dir" ]; then
        echo -e "${RED}❌ Terraform directory '$terraform_dir' does not exist${NC}" >&2
        exit 1
    fi

    # Check if directory contains .tf files
    if [ -z "$(find "$terraform_dir" -name "*.tf" -type f)" ]; then
        echo -e "${RED}❌ No .tf files found in '$terraform_dir'${NC}" >&2
        exit 1
    fi

    # Create output directory
    mkdir -p "$(dirname "$output_file")"

    echo -e "${BLUE}🔄 Processing Terraform configuration...${NC}"
    echo -e "  📁 Source: $terraform_dir"
    echo -e "  📄 Output: $output_file"

    # Build command arguments
    local cmd_args=("--source" "terraform:input")

    if [ "$VERBOSE" = true ]; then
        cmd_args+=("--verbose")
    fi

    if [ "$DEBUG" = true ]; then
        cmd_args+=("--debug")
    fi

    if [ "$VALIDATE" = false ]; then
        cmd_args+=("--no-validate")
    fi

    cmd_args+=("output/$(basename "$output_file")")

    # Run ReTOSCA
    if [ "$COMPOSE_FILE" = "docker-compose-standalone.yml" ]; then
        # Standalone version with automatic volume mounting
        TERRAFORM_DIR="$terraform_dir" OUTPUT_DIR="$(dirname "$output_file")" \
            $DOCKER_COMPOSE -f "$COMPOSE_FILE" run --rm retosca "${cmd_args[@]}"
    else
        # Regular version with manual volume mounting
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" run --rm \
            -v "$(realpath "$terraform_dir"):/app/input:ro" \
            -v "$(realpath "$(dirname "$output_file")"):/app/output" \
            retosca "${cmd_args[@]}"
    fi

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ TOSCA file generated successfully: $output_file${NC}"

        if [ -f "$output_file" ]; then
            echo -e "${YELLOW}📊 Generated file size: $(du -h "$output_file" | cut -f1)${NC}"
        fi
    else
        echo -e "${RED}❌ ReTOSCA processing failed${NC}" >&2
        exit 1
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -d|--debug)
            DEBUG=true
            shift
            ;;
        --no-validate)
            VALIDATE=false
            shift
            ;;
        --standalone)
            COMPOSE_FILE="docker-compose-standalone.yml"
            shift
            ;;
        --extract-examples)
            check_prerequisites
            extract_examples
            exit 0
            ;;
        --validate-only)
            check_prerequisites
            validate_only
            exit 0
            ;;
        --shell)
            check_prerequisites
            start_shell
            exit 0
            ;;
        -*)
            echo -e "${RED}❌ Unknown option: $1${NC}" >&2
            show_usage
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

# Check prerequisites
check_prerequisites

# Handle remaining arguments
if [ $# -eq 0 ]; then
    echo -e "${RED}❌ No terraform directory specified${NC}" >&2
    show_usage
    exit 1
fi

TERRAFORM_DIR="$1"
OUTPUT_FILE="${2:-output/result.yaml}"

# Run ReTOSCA
run_retosca "$TERRAFORM_DIR" "$OUTPUT_FILE"
