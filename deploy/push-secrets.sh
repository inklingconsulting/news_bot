#!/usr/bin/env bash
# Push the secrets from your local .env into GCP Secret Manager.
# Run this yourself (bash deploy/push-secrets.sh) from the repo root — it reads
# .env locally so the raw values never leave your machine except into your own
# Secret Manager. Safe to re-run; it adds a new version each time.
set -euo pipefail

ENV_FILE="${1:-.env}"
[ -f "$ENV_FILE" ] || { echo "No $ENV_FILE found (run from the repo root)."; exit 1; }

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

put() {
  local name="$1" value="${2:-}"
  if [ -z "$value" ]; then echo "skip $name (empty in .env)"; return; fi
  if ! gcloud secrets describe "$name" >/dev/null 2>&1; then
    gcloud secrets create "$name" --replication-policy=automatic >/dev/null
    echo "created $name"
  fi
  printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
  echo "updated $name"
}

put news_bot-anthropic-api-key  "${ANTHROPIC_API_KEY:-}"
put news_bot-telegram-bot-token "${TELEGRAM_BOT_TOKEN:-}"
put news_bot-telegram-chat-id   "${TELEGRAM_CHAT_ID:-}"
echo "Done. Secrets are in Secret Manager for project: $(gcloud config get-value project 2>/dev/null)"
