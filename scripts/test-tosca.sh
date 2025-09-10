#!/bin/bash
# Script to test generated TOSCA files with Puccini

set -e

if [ $# -lt 1 ]; then
    echo "Usage: $0 <tosca-file> [options]"
    echo "Example: $0 output/test.yaml"
    echo "Example: $0 output/test.yaml -c  # compile to clout"
    exit 1
fi

TOSCA_FILE="$1"
shift

if [ ! -f "$TOSCA_FILE" ]; then
    echo "Error: TOSCA file not found: $TOSCA_FILE"
    exit 1
fi

echo "Testing TOSCA file: $TOSCA_FILE"
echo "===================="

# Validate TOSCA syntax
echo "🔍 Validating TOSCA syntax..."
if puccini-tosca parse "$TOSCA_FILE" > /dev/null 2>&1; then
    echo "✅ TOSCA syntax is valid"
else
    echo "❌ TOSCA syntax validation failed"
    puccini-tosca parse "$TOSCA_FILE"
    exit 1
fi

# Compile to clout if requested
if [[ "$*" == *"-c"* ]]; then
    echo ""
    echo "🔧 Compiling to clout..."
    puccini-tosca compile -c "$TOSCA_FILE"
else
    echo ""
    echo "💡 Use -c flag to compile to clout format"
fi

echo ""
echo "✅ TOSCA test completed successfully!"
