# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
CLI-based personal expense categorization system with automated category mapping and account allocation. The system uses AWS Lambda + DynamoDB backend with Google Gemini AI for auto-categorization.

## Architecture
- **Backend**: FastAPI on AWS Lambda with DynamoDB single-table design
- **Frontend**: Python CLI using Click/Typer with Rich for output formatting
- **AI**: Google Gemini API for expense categorization
- **Authentication**: AWS SigV4 via API Gateway
- **Deployment**: Serverless Framework

## Development Commands
- Backend setup: `cd backend && pip install -r requirements.txt`
- Backend deployment: `cd backend && npm run deploy`
- CLI setup: `cd cli && pip install -e .`
- Run CLI: `expense-tracker --help`
- Local development: `uvicorn main:app --reload` (for FastAPI backend)

## Code Structure
- `/docs/epic.md` - Complete technical requirements and specifications
- Backend will use FastAPI with Pydantic v2 for type safety
- CLI will use httpx with AWS4Auth for SigV4 authentication
- Single-table DynamoDB design for data persistence

### Backend File Organization (Local vs AWS)

The backend uses **file naming conventions** to separate local development from AWS deployment:

**AWS Production Files** (deployed to Lambda):
- `main.py` - Lambda handler entry point
- `app_factory.py` - FastAPI app factory (shared)
- `api_routes.py` - API route definitions (shared)
- `core/` - Core functionality (database, models, dependencies, error handlers)
- `services/` - Business logic (repositories, CSV, categorization, reports, upload)
- `requirements.txt` - Production dependencies

**Local Development Files** (excluded from Lambda package):
- `local_main.py` - Local development server entry point
- `local-run.sh` - Local server startup script
- `docker-compose.yml` - Local DynamoDB container setup
- `run_tests.py` - Test runner script
- `uvicorn` - Uvicorn executable wrapper
- `dev-requirements.txt` - Development-only dependencies
- `pytest.ini` - Test configuration
- `tests/` - Test suite

**Configuration:**
- `serverless.yml` contains package exclusion patterns (lines 46-83)
- Exclusions prevent deployment bloat and keep AWS package size minimal
- File naming pattern: `local_*` prefix indicates local-only files

## Implementation Phases
1. **Skeleton App**: Basic FastAPI + DynamoDB + Serverless deployment
2. **Core Data Management**: CRUD for Owners, Accounts, Categories
3. **Expense Processing**: CSV upload and manual categorization
4. **AI Integration**: Gemini API auto-categorization with learning
5. **Reporting**: Account summaries and export functionality

## Environment Setup
Backend requires: GEMINI_API_KEY, DYNAMODB_TABLE_NAME, AWS_REGION
CLI requires: API_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION

## Key Technical Constraints
- 
  - Production enforcement via serverless.yml throttle configuration
  - Override process: Temporarily increase limits in serverless.yml for development/testing, then redeploy
  - Limits apply per authenticated principal (IAM user/role)
- DynamoDB single-table design pattern
- TLS encryption with AES-256 at rest
- CloudWatch logging for monitoring
- use of pip