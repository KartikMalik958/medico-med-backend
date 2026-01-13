#!/bin/bash
echo "Starting Medical Health Assistant Backend..."
echo ""
echo "Make sure you have:"
echo "1. Created a .env file in med/backend/ with OPENAI_API_KEY"
echo "2. Installed dependencies: pip install -r requirements.txt"
echo ""
cd "$(dirname "$0")"
python main.py






