"""
main.py - Entry point for the Google typing searcher application
"""

import os
import sys
import subprocess
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def ensure_playwright_browsers():
    """Ensure Playwright Chromium browser is installed."""
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
        )
        print("✓ Playwright browser installed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install Playwright browser: {e}")
        sys.exit(1)


def validate_config():
    """Validate required environment variables."""
    api_keys = os.getenv("API_KEYS", "").strip()
    if not api_keys:
        print(
            "⚠ Warning: API_KEYS not set. Authentication will be disabled.\n"
            "  Set API_KEYS in .env to enable API key authentication."
        )
    else:
        print(f"✓ API authentication enabled ({len(api_keys.split(','))} key(s))")

    webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if webhook_secret:
        print("✓ Webhook signing enabled")
    else:
        print("⚠ Warning: WEBHOOK_SECRET not set. Webhooks will not be signed.")

    print("✓ Configuration validated")


def main():
    """Main entry point."""
    print("=" * 60)
    print("Google Typing Searcher with Background Jobs")
    print("=" * 60)

    # Ensure .env exists
    if not Path(".env").exists():
        print("\n⚠ .env file not found. Creating from .env.example...")
        if Path(".env.example").exists():
            import shutil
            shutil.copy(".env.example", ".env")
            print("✓ Created .env from .env.example")
            print("  ⚠ Please update .env with your configuration!")
        else:
            print(
                "✗ Neither .env nor .env.example found.\n"
                "  Please create .env with required variables."
            )
            sys.exit(1)

    print("\nValidating configuration...")
    validate_config()

    print("\nEnsuring Playwright browser is installed...")
    ensure_playwright_browsers()

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    print(f"\n✓ Starting server on {host}:{port}")
    print("=" * 60)
    print("\nAPI Endpoints:")
    print(f"  POST   http://{host}:{port}/search")
    print(f"  GET    http://{host}:{port}/results/{{job_id}}")
    print(f"  Docs   http://{host}:{port}/docs")
    print("=" * 60 + "\n")

    # Import app here to ensure config is loaded
    from app import app

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
