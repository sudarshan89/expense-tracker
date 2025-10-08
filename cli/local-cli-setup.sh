#!/usr/bin/env bash
# Local CLI setup helper script
# Usage: bash cli/local-cli-setup.sh

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Copy .env.local to .env
cp "$SCRIPT_DIR/.env.local" "$SCRIPT_DIR/.env"

echo "Created .env for local development"

# Basic health check
expense-tracker health

# Optional: seed data (if supported by your environment)
expense-tracker seed

# List categories
expense-tracker categories list

# Upload a CSV of expenses (adjust the path if needed)
expense-tracker expenses upload-csv "$HOME/Downloads/activity.csv"

# List expenses for a specific card member
expense-tracker expenses list --limit 300


