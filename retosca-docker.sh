#!/bin/bash

# ReTOSCA Docker Wrapper
# Usage: ./retosca-docker.sh -s terraform:/path/to/terraform /path/to/output.yaml

# Parse arguments exactly like main.py
ARGS=("$@")

# Find source and output paths from arguments
SOURCE_PATH=""
OUTPUT_PATH=""

for i in "${!ARGS[@]}"; do
    if [[ "${ARGS[i]}" == "-s" || "${ARGS[i]}" == "--source" ]]; then
        # Extract path from terraform:/path/to/source format
        SOURCE_ARG="${ARGS[i+1]}"
        SOURCE_PATH="${SOURCE_ARG#terraform:}"
    elif [[ "${ARGS[i]}" != -* ]] && [[ "${ARGS[i]}" != terraform:* ]] && [[ -n "${ARGS[i]}" ]]; then
        # Last non-option argument is output path
        OUTPUT_PATH="${ARGS[i]}"
    fi
done

if [[ -z "$SOURCE_PATH" || -z "$OUTPUT_PATH" ]]; then
    echo "Usage: $0 -s terraform:/path/to/terraform /path/to/output.yaml"
    exit 1
fi

# Get absolute paths
SOURCE_PATH=$(realpath "$SOURCE_PATH")
OUTPUT_DIR=$(dirname "$(realpath "$OUTPUT_PATH")")
OUTPUT_FILE=$(basename "$OUTPUT_PATH")

# Run docker command
docker-compose run --rm \
    -v "$SOURCE_PATH:/app/input" \
    -v "$OUTPUT_DIR:/app/output" \
    retosca \
    python -m src.main -s terraform:/app/input "/app/output/$OUTPUT_FILE"
