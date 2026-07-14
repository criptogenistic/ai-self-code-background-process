#!/bin/bash

# startup.sh - Automated startup script for Google typing searcher

set -e

echo "========================================"
echo "Google Typing Searcher - Startup"
echo "========================================"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 is not installed"
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env from .env.example if needed
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "Creating .env from .env.example..."
        cp .env.example .env
        echo "⚠ Please update .env with your configuration before running!"
    else
        echo "✗ .env.example not found"
        exit 1
    fi
fi

echo ""
echo "========================================"
echo "Setup complete! Starting application..."
echo "========================================"
echo ""

# Run the application
python main.py
