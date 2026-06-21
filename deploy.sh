#!/bin/bash
# deploy.sh – Bare-metal deployment helper for Linux servers
# Usage: chmod +x deploy.sh && ./deploy.sh

set -e

echo "[*] Course Verifier Server Deployment"
echo "========================================"

# 1. Python check
if ! command -v python3 &> /dev/null; then
    echo "[X] python3 not found. Install Python 3.11+ first."
    exit 1
fi

# 2. Virtualenv
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating virtualenv..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 3. Dependencies
echo "[*] Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 4. Chrome check (Linux only)
if ! command -v google-chrome &> /dev/null; then
    echo "[!] Google Chrome not found. Install it for Selenium:"
    echo "    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -"
    echo "    sudo sh -c 'echo \"deb http://dl.google.com/linux/chrome/deb/ stable main\" >> /etc/apt/sources.list.d/google.list'"
    echo "    sudo apt-get update && sudo apt-get install -y google-chrome-stable"
fi

# 5. Env check
if [ ! -f ".env" ]; then
    echo "[!] .env not found. Copy .env.example and fill in your keys."
fi

# 6. Run verifier (pages 602-1890)
echo "[*] Starting verifier for pages 602-1890..."
export VERIFIER_NO_FORCE_EXIT=true
python3 run_verifier_pages.py link_compile.pdf --pages 602 1890

echo "[*] Verification complete. Starting dashboard on port 8080..."
python3 dashboard.py
