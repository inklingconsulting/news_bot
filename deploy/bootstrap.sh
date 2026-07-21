#!/usr/bin/env bash
# VM startup script — provisions and (re)deploys news_bot on a fresh GCE VM.
# Passed to the instance as metadata `startup-script`; runs as root on every boot.
# Idempotent: safe to re-run to pick up new code or secrets.
set -euo pipefail

REPO_URL="https://github.com/inklingconsulting/news_bot.git"
APP_DIR="/opt/bots/news_bot"

echo "[bootstrap] installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git

echo "[bootstrap] ensuring botrunner user + /opt/bots"
id botrunner &>/dev/null || useradd -m -s /bin/bash botrunner
install -d -o botrunner -g botrunner /opt/bots

echo "[bootstrap] clone/update + install deps (as botrunner)"
sudo -u botrunner bash <<EOF
set -euo pipefail
cd /opt/bots
if [ -d news_bot/.git ]; then
  git -C news_bot pull --ff-only
else
  git clone "$REPO_URL"
fi
cd news_bot
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
EOF

echo "[bootstrap] writing .env from Secret Manager"
fetch() { gcloud secrets versions access latest --secret="$1" 2>/dev/null || true; }
umask 077
{
  echo "ANTHROPIC_API_KEY=$(fetch news_bot-anthropic-api-key)"
  echo "TELEGRAM_BOT_TOKEN=$(fetch news_bot-telegram-bot-token)"
  echo "TELEGRAM_CHAT_ID=$(fetch news_bot-telegram-chat-id)"
  echo "MODEL=claude-opus-4-8"
  echo "TIMEZONE=America/New_York"
  echo "BRIEF_HOUR=7"
  echo "BRIEF_MINUTE=0"
} > "$APP_DIR/.env"
chown botrunner:botrunner "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

echo "[bootstrap] installing + starting systemd service"
cp "$APP_DIR/deploy/systemd/news_bot.service" /etc/systemd/system/news_bot.service
systemctl daemon-reload
systemctl enable --now news_bot
echo "[bootstrap] done"
