# Repository Guidelines

## Project Structure & Module Organization
- `backend/` contains the FastAPI service packaged for AWS Lambda. Core modules live under `backend/core/` (models, database helpers) and `backend/services/` (repositories, categorisation, CSV ingestion). API routes sit in `backend/api_routes.py`; `local_main.py` bootstraps the app for Uvicorn.
- `backend/tests/` hosts pytest suites for models, repositories, API routes, CLI integration, and CSV upload logic. Test data lives inline with each module.
- `cli/` provides the Click-based command-line client (`cli/main.py`) and packaging metadata. Seed commands and interactive flows dispatch through the `expense-tracker` entry point.
- `docs/` stores epics, user stories, and roadmap artefacts; treat them as the authorative product spec.

## Build, Test, and Development Commands
- Install backend deps: `cd backend && pip install -r requirements.txt`. Add `pip install -r dev-requirements.txt` when linting locally.
- Run the API locally: `cd backend && uvicorn local_main:app --reload` (uses the in-memory Dynamo stub when `ENVIRONMENT=local`).
- Execute tests: `cd backend && python -m pytest` for the full suite, or `python backend/run_tests.py` for curated checks.
- Install the CLI: `cd cli && pip install -e .`, then call `expense-tracker health` to verify connectivity.

## Coding Style & Naming Conventions
- Target Python 3.10+, four-space indentation, and PEP 8 spacing. Use `snake_case` for functions/variables, `PascalCase` for Pydantic models, and keep docstrings terse with business context.
- Repositories must preserve Dynamo key helpers (`get_pk`, `get_sk`) and descriptive method names. Surface validation through Pydantic validators rather than inline `if` chains.

## Testing Guidelines
- Pytest is the standard harness; name files `test_<feature>.py` and keep fixtures reusable via `backend/tests/conftest.py`.
- Exercise new repository logic with both happy-path and failure cases. When adding curated smoke suites, extend `backend/run_tests.py` so contributors share a single entry point.

## Commit & Pull Request Guidelines
- Use short, imperative commit subjects (e.g., `backend: add expense filters`). Reference relevant docs or stories when appropriate and summarise validation commands in the body.
- PRs should capture scope, list validation steps (`python backend/run_tests.py`, CLI transcripts, screenshots as needed), and flag new environment variables or infrastructure changes early.

## Security & Configuration Tips
- Never commit populated `.env` files; start from `cli/.env.example` when configuring `API_ENDPOINT` and AWS credentials.
- Lambda deployments depend on `DYNAMODB_TABLE_NAME`, `AWS_REGION`, and `LOG_LEVEL`. Document default values in PRs when they change, and confirm throttling settings remain aligned with the stage configuration.
