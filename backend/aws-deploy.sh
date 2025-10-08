
# Install Node dependencies (Serverless Framework)
npm install


python -m venv .venv

source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
pip install "python-dotenv[cli]"  # ensure CLI is available

python -m dotenv -f .env run -- printenv ENVIRONMENT


# Deploy to AWS with env loaded from .env
python -m dotenv -f .env run -- npm run deploy
