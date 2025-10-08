# Expense Tracker App - Technical Requirements Document

## Project Overview

**Goal**: Build a CLI-based personal expense categorization system with automated category mapping and account allocation.

**Core Workflow**:
1. User uploads CSV file with expense data
2. System auto-categorizes expenses using existing mappings
3. Unknown expenses are categorized via Gemini AI and flagged for review
4. User confirms/edits categorizations
5. System remembers manual categorizations for future use
6. Expenses are mapped to payment accounts for tracking

## Architecture

```
┌─────────────┐     HTTPS/SigV4      ┌──────────────┐
│   CLI App   │ ◄──────────────────► │ API Gateway  │
│  (Python)   │                       │  (HTTP API)  │
└─────────────┘                       └──────────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │  Lambda Function│
                                    │   (FastAPI)     │
                                    └─────────────────┘
                                             │
                                    ┌────────┴────────┐
                                    ▼                 ▼
                            ┌──────────────┐  ┌──────────────┐
                            │   DynamoDB   │  │  Gemini API  │
 ```

## Technical Stack

### Backend
- **Language**: Python 3
- **Framework**: FastAPI
- **Type Safety**: Pydantic v2
- **Database**: DynamoDB (single-table design recommended)
- **AI Service**: Google Gemini API (free tier)
- **Deployment**: AWS Lambda + Serverless Framework
- **Authentication**: AWS IAM (SigV4)
- **API Gateway**: AWS HTTP API with rate limiting (5 req/min)

### CLI Client
- **Framework**: Click
- **HTTP Client**: requests with aws-requests-auth (SigV4)
- **Configuration**: python-dotenv for environment variables
- **Output**: Rich tables for formatted display

## Implementation Phases

### Epic 1: Skeleton App (MVP for deployment validation)
- Basic FastAPI app with health check endpoint
- DynamoDB table creation
- Serverless deployment configuration
- API Gateway setup with IAM auth
- Basic CLI with authenticated API call
- CloudWatch logging setup

### Epic 2: Core Data Management
- CRUD operations for Owners, Accounts, Categories, Expenses
- CLI commands for entity management
- References ./stories.md + E2:Core Data Management for more details

### Epic 3: Expense processing
- CSV upload and parsing
- Expense persistence
- Auto-categorization logic: historical matches (last 3 months), deterministic label substring matching with card-member priority, Unknown fallback with DynamoDB `category_hint` list (persisted as a list, even when empty)
- AI-based categorization recommendations for unknown expenses inputting into manual categorization workflow
- Updating categorization labels based on user input
- References ./stories.md + E3: Expense processing for more details

### Epic 4: AI Integration (De-prioritized)
- Gemini API integration
- Auto-categorization logic
- Learning from manual categorizations

### Epic 5: Reporting
- Account-based expense grouping and summaries
- Expenses by account report with filtering (date range, category, card member)
- CLI report commands with summary and detailed views
- REST endpoint for programmatic access to reports
- Export functionality (future enhancement)
- References ./stories.md + E5: Reporting & Analytics

## Security Requirements
- TLS encryption for all API communication
- AES-256 encryption at rest (DynamoDB default)
- API rate limiting via API Gateway stage throttle (~5 requests/minute sustained, short burst of 5)
- IAM-based authentication
- Input validation on all endpoints
- Sanitize CSV uploads

## Monitoring & Observability
- **Current**
  - CloudWatch Logs for all Lambda invocations
  - Standard AWS metrics (Lambda duration, errors, throttles; API Gateway 4XX/5XX)
- **Target Enhancements**
  - Custom metrics for categorization accuracy, API response times, and error rates
  - Alarms for high error rates, rate-limit breaches, and Lambda timeouts

## Environment Variables

### Backend Environment
```
GEMINI_API_KEY=
DYNAMODB_TABLE_NAME=expense-tracker
AWS_REGION=ap-southeast-2
LOG_LEVEL=INFO
ENVIRONMENT=
AWS_DEFAULT_REGION=
```

`ENVIRONMENT=local` enables the in-memory DynamoDB stub during development. For deployed stages leave it empty or set a named stage.

### CLI Environment
```
API_ENDPOINT=https://xxx.execute-api.ap-southeast-2.amazonaws.com
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-southeast-2
ENVIRONMENT=
```

When targeting a deployed API, set `API_ENDPOINT` and AWS credentials (SigV4). For local Uvicorn usage, point `API_ENDPOINT` to `http://localhost:8000` and set `ENVIRONMENT=local` so the CLI skips SigV4.

## Success Metrics
- Deployment completes successfully
- Health check endpoint responds with 200 OK
- CLI can authenticate and call API
- DynamoDB table is accessible
- CloudWatch logs are being generated
- Rate limiting is enforced
