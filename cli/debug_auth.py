#!/usr/bin/env python3
"""Debug script to test AWS authentication."""

import os

import requests
from aws_requests_auth.aws_auth import AWSRequestsAuth
from dotenv import load_dotenv

load_dotenv()


def debug_aws_auth():
    """Debug AWS authentication setup."""

    # Load environment variables
    api_endpoint = os.getenv("API_ENDPOINT")
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION", "ap-southeast-2")
    environment = os.getenv("ENVIRONMENT")

    print("=== Environment Variables ===")
    print(f"ENVIRONMENT: {environment}")
    print(f"API_ENDPOINT: {api_endpoint}")
    print(
        f"AWS_ACCESS_KEY_ID: {aws_access_key_id[:10]}..."
        if aws_access_key_id
        else "None"
    )
    print(f"AWS_SECRET_ACCESS_KEY: {'*' * 20}" if aws_secret_access_key else "None")
    print(f"AWS_REGION: {aws_region}")

    # Check if running in local mode
    is_local = api_endpoint and (
        api_endpoint.startswith("http://localhost")
        or api_endpoint.startswith("http://127.0.0.1")
        or environment == "local"
    )

    print(f"\nIs Local Development: {is_local}")

    if is_local:
        print("Running in local mode - no authentication needed")
        return

    # Extract host from API endpoint
    host = api_endpoint.replace("https://", "").replace("http://", "").rstrip("/")
    print(f"AWS Host: {host}")

    # Create AWS auth
    try:
        auth = AWSRequestsAuth(
            aws_access_key=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_token=os.getenv("AWS_SESSION_TOKEN"),
            aws_host=host,
            aws_region=aws_region,
            aws_service="execute-api",
        )
        print("✅ AWS Auth object created successfully")
    except Exception as e:
        print(f"❌ Failed to create AWS Auth: {e}")
        return

    # Test request with detailed logging
    url = f"{api_endpoint.rstrip('/')}/health"
    print(f"\nTesting request to: {url}")

    try:
        # Make request with auth
        response = requests.get(url, auth=auth)
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text}")

        # Check if we have authorization header
        if hasattr(auth, "add_auth"):
            print("\n=== Checking Auth Headers ===")
            # Create a dummy request to see what headers are added
            from requests import Request

            req = Request("GET", url)
            prepped = req.prepare()
            auth.add_auth(prepped)

            print("Authorization headers that would be added:")
            for header, value in prepped.headers.items():
                if "auth" in header.lower() or "aws" in header.lower():
                    print(f"  {header}: {value}")

    except Exception as e:
        print(f"❌ Request failed: {e}")


if __name__ == "__main__":
    debug_aws_auth()
