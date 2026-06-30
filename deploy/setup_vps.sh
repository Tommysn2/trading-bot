#!/bin/bash
# =============================================================
# Trading Bot — Hetzner VPS Setup Script
# Run this as root on a fresh Ubuntu 22.04 server.
# Usage: bash setup_vps.sh <your_github_username>
# =============================================================

set -e  # Exit on any error

GITHUB_USER="${1:-your_github_username}"
REPO_NAME="trading-bot"
BOT_DIR="/opt/trading-bot"
SERVICE_NAME="trading-bot"
PYTHON_MIN="3.10"

echo ""
echo "=================================================="
echo "  Trading Bot VPS Setup"
echo "  Repo: github.com/${GITHUB_USER}/${REPO_NAME}"
echo "=================================================="
echo ""

# ── System packages ──────────────────────────────────────────
echo "[1/6] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl

PYTHON_VER=$(python3 --version | cut -d' ' -f2)
echo "      Python: $PYTHON_VER"

# ── Clone repo ───────────────────────────────────────────────
echo "[2/6] Cloning repository..."
if [ -d "$BOT_DIR" ]; then
    echo "      Directory exists — pulling latest..."
    cd "$BOT_DIR"
    git pull
else
    git clone "https://github.com/${GITHUB_USER}/${REPO_NAME}.git" "$BOT_DIR"
    cd "$BOT_DIR"
fi

# ── Python virtual environment ───────────────────────────────
echo "[3/6] Setting up Python virtual environment..."
python3 -m venv "$BOT_DIR/venv"
source "$BOT_DIR/venv/bin/activate"
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "      Dependencies installed."

# ── Environment file ─────────────────────────────────────────
echo "[4/6] Setting up .env file..."
if [ ! -f "$BOT_DIR/.env" ]; then
    cp "$BOT_DIR/.env.example" "$BOT_DIR/.env"
    echo ""
    echo "  ⚠️  ACTION REQUIRED: Edit your .env file now:"
    echo "      nano $BOT_DIR/.env"
    echo ""
    echo "  Fill in:"
    echo "    ALPACA_API_KEY"
    echo "    ALPACA_SECRET_KEY"
    echo "    ANTHROPIC_API_KEY"
    echo "    SUPABASE_URL"
    echo "    SUPABASE_KEY"
    echo "    TELEGRAM_BOT_TOKEN"
    echo "    TELEGRAM_CHAT_ID"
    echo ""
    read -p "  Press ENTER after you've saved your .env file..."
else
    echo "      .env already exists — skipping."
fi

# ── Test connections ─────────────────────────────────────────
echo "[5/6] Testing all API connections..."
source "$BOT_DIR/venv/bin/activate"
cd "$BOT_DIR"
python test_connections.py
echo ""

# ── Systemd service ──────────────────────────────────────────
echo "[6/6] Installing systemd service..."
cp "$BOT_DIR/deploy/trading-bot.service" "/etc/systemd/system/${SERVICE_NAME}.service"

# Patch the service file with the correct paths
sed -i "s|/opt/trading-bot|${BOT_DIR}|g" "/etc/systemd/system/${SERVICE_NAME}.service"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

echo ""
echo "=================================================="
echo "  ✅ Setup complete!"
echo ""
echo "  Bot is running. Commands:"
echo "    Status:  systemctl status ${SERVICE_NAME}"
echo "    Logs:    journalctl -u ${SERVICE_NAME} -f"
echo "    Stop:    systemctl stop ${SERVICE_NAME}"
echo "    Restart: systemctl restart ${SERVICE_NAME}"
echo "    Update:  cd ${BOT_DIR} && git pull && systemctl restart ${SERVICE_NAME}"
echo "=================================================="
echo ""
echo "  Check your Telegram — you should receive a 'Bot started' message."
echo ""
