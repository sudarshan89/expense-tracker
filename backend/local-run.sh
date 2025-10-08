#!/usr/bin/env bash
set -Eeuo pipefail
# Install Node dependencies (Serverless Framework)
npm install

python -m venv .venv

source .venv/bin/activate

# Install Python dependencies
pip install -r dev-requirements.txt
pip install "python-dotenv[cli]"  # ensure CLI is available

python -m dotenv -f .env.local run -- printenv ENVIRONMENT

docker-compose up -d
sleep 3
python -m dotenv -f .env.local run -- python -m pytest
python -m dotenv -f .env.local run -- uvicorn local_main:app --reload
