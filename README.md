# Expense Tracker

Personal expense categorization system with AWS Lambda backend and Python CLI. Features automated AI-powered category mapping, account allocation, and CSV import.

---

## Prerequisites

- **AWS Account** with CLI configured (`aws configure`)
- **Python 3.11+**
- **Node.js 16+** (for Serverless Framework)
- **Gemini API Key** (for auto-categorization) - Get from [Google AI Studio](https://aistudio.google.com/app/apikey)

---

## Deployment

### 1. Deploy Backend to AWS

```bash
# Navigate to backend directory
cd backend
sh ./aws-deploy.sh
```

**Expected output:**
```
✔ Service deployed to stack expense-tracker-dev

endpoints:
  ANY - https://xxxxxxxxxx.execute-api.ap-southeast-2.amazonaws.com/{proxy+}
  ANY - https://xxxxxxxxxx.execute-api.ap-southeast-2.amazonaws.com/
```

**Save the API endpoint URL** - you'll need it for CLI configuration.

---

### 2. Configure and Install CLI

**Automated Setup (Recommended)**

```bash
# Navigate to CLI directory
cd ../cli

# Install CLI package
pip install -e .

# Run setup script (creates .env, seeds data, verifies deployment)
bash aws-cli-setup.sh https://xxxxxxxxxx.execute-api.ap-southeast-2.amazonaws.com
```
---

## Understanding Seed Data

Before seeding, understand the data model:

**Data Hierarchy:** Owners → Accounts → Categories → Expenses

1. **Owners**: Represent card holders (e.g., "John", "Jane")
   - Have a `card_name` field matching the name on credit card statements (e.g., "J Doe")

2. **Accounts**: Financial accounts tied to owners (e.g., "Pocket-Money John", "Groceries Jane")
   - Each account has a unique `account_id` = `account_name + owner_name` because two owners can have the same account name (e.g., "Pocket-Money")
   - Accounts are linked to owners via `owner_name`
   - Expenses are allocated to accounts via categories

3. **Categories**: Define how expenses are auto-categorized (e.g., "JohnSpend", "Groceries")
   - Each category has `labels` (keywords that match expense descriptions)
   - Categories are linked to a specific account via `account_id`
   - When an expense matches a category label, it's assigned to that category's account

**Example:**
```yaml
# Owner
- name: John
  card_name: J Doe

# Account
- account_name: Pocket-Money
  owner_name: John
  # account_id = "Pocket-Money John"

# Category with labels
- name: JohnSpend
  account_id: Pocket-Money John
  card_name: J Doe
  labels:
    - coffee
    - cafe
    - UBER
```

When you upload a CSV with description "UBER TRIP", it will:
1. Match the "UBER" label in "JohnSpend" category
2. Assign category = "JohnSpend"
3. Allocate expense to account = "Pocket-Money John"

---

### 4. Customize and Seed Your Data

**Step 1: Create your seed data file**

```bash
# Copy the example seed data
cp cli/seed_data_example.yaml cli/seed_data.yaml

# Edit with your personal data
nano cli/seed_data.yaml  # or use your preferred editor
```

**Step 2: Update the seed data with your information**

Edit `cli/seed_data.yaml`:
- Replace example names with your actual names
- Update card_name to match names on your credit card statements exactly
- Configure accounts that match your bank accounts
- Add categories with labels that match common merchant names in your statements

**Step 3: Load the data**

```bash
# Load owners, accounts, and categories from seed_data.yaml
expense-tracker seed

# Expected output:
# Starting database seed...
#
# Owners:
#   ✓ John
#   ✓ Jane
#   2 created, 0 skipped
#
# Accounts:
#   ✓ Pocket-Money (John)
#   ✓ Groceries (Jane)
#   ...
#   13 created, 0 skipped
#
# Categories:
#   ✓ Water
#   ✓ Apple
#   ✓ JohnSpend
#   ...
#   11 created, 0 skipped
#
# ✓ Seed complete!
```

**Note:** The seed command is idempotent - running it multiple times is safe. Existing entities will be skipped.

**Deployment complete!** 🚀

---

## Common Commands

### Manage Expenses
```bash
# Create expense manually
expense-tracker expenses create --date 2025-01-15 --description "Coffee" --card-member "J Doe" --amount 5.50

# Upload CSV file
expense-tracker expenses upload-csv expenses.csv

# List expenses
expense-tracker expenses list --start-date 2025-01-01 --end-date 2025-01-31

# Update expense category
expense-tracker expenses update <expense-id> --category Groceries
```

### Generate Reports
```bash
# Monthly report (11th to 11th billing cycle)
expense-tracker reports expenses-by-account --month Jan

# Custom date range
expense-tracker reports expenses-by-account --start-date 2025-01-01 --end-date 2025-01-31
```

### Manage Data
```bash
# List owners
expense-tracker owners list

# List accounts
expense-tracker accounts list

# List categories
expense-tracker categories list
```

---

## Local Development (Optional)

For development without deploying to AWS:

```bash
# Terminal 1: Start local API server
cd backend
sh ./local-run.sh
```

```bash
# Terminal 2: Configure CLI for local use
cd cli
bash local-cli-setup.sh  # Creates .env, seeds data, runs tests
```

This setup script:
- Copies `.env.local` to `.env` (configured for http://localhost:8000)
- Runs health check
- Seeds initial data
- Lists categories to verify setup

---

## Teardown

```bash
# Remove AWS resources
cd backend
npm run remove

# Uninstall CLI
cd ../cli
pip uninstall expense-tracker-cli
```

---

## Configuration Reference

### Backend Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key for auto-categorization | Required |
| `ENVIRONMENT` | Set to `local` for local development | `production` |
| `DYNAMODB_TABLE_NAME` | DynamoDB table name | `expense-tracker-prod` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |

### CLI Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `API_ENDPOINT` | Backend API URL | Yes |
| `AWS_ACCESS_KEY_ID` | AWS access key for SigV4 auth | Yes (production) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key for SigV4 auth | Yes (production) |
| `AWS_REGION` | AWS region | No (default: `ap-southeast-2`) |

---

## Architecture

**Backend:**
- FastAPI application running on AWS Lambda
- Mangum ASGI adapter for Lambda compatibility
- DynamoDB single-table design with GSI indexes
- Python 3.11 runtime

**CLI:**
- Click framework for command interface
- Rich library for formatted output
- AWS SigV4 authentication for API requests
- YAML-based seed data configuration

**Deployment:**
- Serverless Framework for infrastructure as code
- Automated exclusion of local development files
- Pay-per-request DynamoDB billing
- CloudWatch logging enabled

---

## Troubleshooting

**API health check fails:**
- Verify API endpoint URL in `cli/.env`
- Check AWS credentials are correct
- Ensure IAM user has API Gateway invoke permissions

**Seed command fails:**
- Run `expense-tracker seed` multiple times (handles duplicates gracefully)
- Check DynamoDB table exists in AWS console
- Verify Lambda logs: `cd backend && npm run logs`

**Deployment fails:**
- Ensure `GEMINI_API_KEY` environment variable is set
- Check AWS CLI is configured: `aws sts get-caller-identity`
- Verify Serverless Framework is installed: `npx serverless --version`

**Expenses not auto-categorizing:**
- Verify `GEMINI_API_KEY` is set in Lambda environment variables
- Check CloudWatch logs for API errors
- Ensure categories with matching labels exist

---

## Documentation

- **Full Requirements:** `docs/epic.md`
- **User Stories:** `docs/stories.md`
- **Seed Data Example:** `cli/seed_data_example.yaml` (copy to `seed_data.yaml` and customize)
- **Development Guide:** `CLAUDE.md`

---

## Support

For issues, check CloudWatch logs:
```bash
cd backend
npm run logs
```

Or run tests locally:
```bash
cd backend
python -m pytest -v
```
