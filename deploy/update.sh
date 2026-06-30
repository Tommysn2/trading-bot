#!/bin/bash
# One-command bot update — pull latest code and restart.
# Run from VPS: bash /opt/trading-bot/deploy/update.sh

cd /opt/trading-bot
git pull
source venv/bin/activate
pip install -r requirements.txt -q
systemctl restart trading-bot
echo "✅ Bot updated and restarted."
journalctl -u trading-bot -n 20 --no-pager
