#!/bin/bash

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
E2E_DIR="tests/e2e"
HURL_OPTIONS="--test --color --verbose"

echo -e "${YELLOW}🧪 Running E2E tests with Hurl${NC}"

# Check if hurl is installed
if ! command -v hurl &> /dev/null; then
    echo -e "${RED}❌ Error: hurl is not installed${NC}"
    echo "Install with: pacman -S hurl"
    exit 1
fi

# Check if tests directory exists
if [ ! -d "$E2E_DIR" ]; then
    echo -e "${RED}❌ Error: $E2E_DIR directory not found${NC}"
    exit 1
fi

# Check if there are any .hurl files
HURL_FILES=$(find "$E2E_DIR" -name "*.hurl" -o -name "*.http" 2>/dev/null || true)
if [ -z "$HURL_FILES" ]; then
    echo -e "${RED}❌ Error: No .hurl or .http files found in $E2E_DIR${NC}"
    exit 1
fi

# Check if docker compose is running
echo -e "${YELLOW}🔍 Checking if docker compose services are running...${NC}"
if ! docker compose ps --services --filter "status=running" &> /dev/null; then
    echo -e "${RED}❌ Error: No docker compose services are running${NC}"
    echo "Start with: docker compose up -d"
    exit 1
fi

RUNNING_SERVICES=$(docker compose ps --services --filter "status=running" | wc -l)
echo -e "${GREEN}✅ Found $RUNNING_SERVICES running docker compose services${NC}"

# Wait for services to be ready (optional health check)
echo -e "${YELLOW}⏳ Waiting for services to be ready...${NC}"
sleep 2

# Run all hurl files
FAILED_TESTS=()
PASSED_TESTS=()
TOTAL_TESTS=0

echo -e "${YELLOW}🚀 Running tests...${NC}"
echo

for file in $HURL_FILES; do
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo -e "${YELLOW}📋 Running: $(basename "$file")${NC}"
    
    if hurl $HURL_OPTIONS "$file"; then
        echo -e "${GREEN}✅ PASSED: $(basename "$file")${NC}"
        PASSED_TESTS+=("$(basename "$file")")
    else
        echo -e "${RED}❌ FAILED: $(basename "$file")${NC}"
        FAILED_TESTS+=("$(basename "$file")")
    fi
    echo
done

# Summary
echo -e "${YELLOW}📊 Test Summary${NC}"
echo "======================"
echo -e "Total tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: ${#PASSED_TESTS[@]}${NC}"
echo -e "${RED}Failed: ${#FAILED_TESTS[@]}${NC}"

if [ ${#FAILED_TESTS[@]} -gt 0 ]; then
    echo
    echo -e "${RED}❌ Failed tests:${NC}"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
    exit 1
else
    echo
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    exit 0
fi
