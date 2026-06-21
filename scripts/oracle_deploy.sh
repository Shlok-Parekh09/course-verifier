#!/bin/bash
# ==============================================================================
#  Deploy Course Verifier on Oracle Cloud Free Tier (ARM Ampere A1)
#  ------------------------------------------------------------------------------
#  This script sets up a fully working verifier on Oracle Cloud.
#  The ARM instance gives you 4 OCPU + 24 GB RAM — absolutely free forever.
#
#  Prerequisites:
#    1. Sign up at https://www.oracle.com/cloud/free/
#    2. Create an Ampere A1 instance (VM.Standard.A1.Flex, 4 OCPU, 24 GB)
#    3. SSH into the instance
#    4. Run:  curl -fsSL https://raw.githubusercontent.com/Shlok-Parekh09/course-verifier/yug-render-deploy/scripts/oracle_deploy.sh | bash
# ==============================================================================
set -euo pipefail

REPO_URL="https://github.com/Shlok-Parekh09/course-verifier.git"
BRANCH="yug-render-deploy"
INSTALL_DIR="$HOME/course-verifier"
LOG_FILE="$HOME/verifier-setup.log"

echo "======================================"
echo " Course Verifier — Oracle Cloud Setup "
echo "======================================"

# ── 1. System update ──
echo "[1/7] Updating system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    git wget curl unzip ca-certificates gnupg2 \
    fonts-liberation libglib2.0-0 libnss3 libgconf-2-4 \
    libfontconfig1 libxss1 libappindicator3-1 libatk-bridge2.0-0 \
    libgtk-3-0 libxcomposite1 libxcursor1 libxdamage1 libxi6 \
    libxtst6 libxrandr2 libasound2 libpangocairo-1.0-0 \
    libatspi2.0-0 libcups2 libdrm2 libgbm1 libxkbcommon0 \
    tesseract-ocr tesseract-ocr-eng python3-pip python3-venv \
    cron mailutils

# ── 2. Install Google Chrome ──
echo "[2/7] Installing Google Chrome..."
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add - 2>/dev/null || true
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list'
sudo apt-get update -qq
sudo apt-get install -y -qq google-chrome-stable

# ── 3. Clone repo ──
echo "[3/7] Cloning repository..."
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR"
    git fetch origin
    git reset --hard "origin/$BRANCH"
else
    git clone -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ── 4. Python environment ──
echo "[4/7] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
playwright install chromium || true

# ── 5. Create .env from template ──
echo "[5/7] Creating .env template..."
if [ ! -f ".env" ]; then
    cat > .env <<'EOF'
# ── Fill these with your actual secrets ──
OPENROUTER_KEY_1=
GEMINI_KEY_1=
OLLAMA_API_URL=
OLLAMA_MODEL=
OLLAMA_API_KEY=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
SMTP_FROM=
SMTP_TO=yugshah197@gmail.com
SEND_EMAIL_ON_COMPLETE=true
VERIFIER_NO_FORCE_EXIT=true
EOF
    chmod 600 .env
    echo "⚠️  Please edit .env and add your API keys / SMTP credentials!"
    echo "   Run:  nano ~/course-verifier/.env"
fi

# ── 6. Supervisor / Systemd service for background running ──
echo "[6/7] Creating systemd service..."
sudo tee /etc/systemd/system/verifier.service > /dev/null <<EOF
[Unit]
Description=Course Verifier
After=network.target

[Service]
Type=oneshot
User=$USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="VERIFIER_NO_FORCE_EXIT=true"
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/run_verifier_pages.py $INSTALL_DIR/link_compile.pdf --pages 602 1890 --no-email
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable verifier.service

# ── 7. Cron job for weekly runs ──
echo "[7/7] Setting up weekly cron job..."
(crontab -l 2>/dev/null || true; echo "0 2 * * 0 cd $INSTALL_DIR && source venv/bin/activate && VERIFIER_NO_FORCE_EXIT=true python run_verifier_pages.py link_compile.pdf --pages 602 1890 --no-email >> $HOME/verifier-cron.log 2>&1") | sort -u | crontab -

# ── Done ──
cat <<'MESSAGE'

========================================
✅  SETUP COMPLETE!
========================================

Next steps:
1. Upload link_compile.pdf to:  ~/course-verifier/
2. Edit secrets:                  nano ~/course-verifier/.env
3. Test manually:                 cd ~/course-verifier && source venv/bin/activate && python run_verifier_pages.py link_compile.pdf --pages 602 1890
4. Run via systemd:               sudo systemctl start verifier
5. Check status:                  sudo journalctl -u verifier -f

The verifier also runs automatically every Sunday at 2 AM (cron).
Logs are saved to:  ~/verifier-setup.log  and  ~/verifier-cron.log

========================================
MESSAGE
