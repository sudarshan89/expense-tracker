#!/usr/bin/env bash
# AWS CLI setup helper script
# Usage: bash cli/aws-cli-setup.sh <API_ENDPOINT>

# Require API endpoint
if [ -z "$1" ]; then
    echo "Error: API endpoint required"
    echo "Usage: $0 <API_ENDPOINT>"
    echo "Example: $0 https://abc123.execute-api.ap-southeast-2.amazonaws.com"
    exit 1
fi

API_ENDPOINT="$1"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Copy .env.example to .env
cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"

# Update API_ENDPOINT in .env
sed -i '' "s|API_ENDPOINT=.*|API_ENDPOINT=$API_ENDPOINT|" "$SCRIPT_DIR/.env"

echo "Created .env with API_ENDPOINT=$API_ENDPOINT"

# Test health check
expense-tracker health

expense-tracker seed

# List categories
expense-tracker categories list
