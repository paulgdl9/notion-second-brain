#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SECRETS_FILE="$ROOT/.env"

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "missing $SECRETS_FILE" >&2
  exit 1
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

awk -F= '
  BEGIN {
    memo = "MEMO_TOKEN=" ENVIRON["MEMO_TOKEN"]
    capture = "CAPTURE_TOKEN=" ENVIRON["CAPTURE_TOKEN"]
  }
  /^MEMO_TOKEN=/ && ENVIRON["MEMO_TOKEN"] != "" { print memo; next }
  /^CAPTURE_TOKEN=/ && ENVIRON["CAPTURE_TOKEN"] != "" { print capture; next }
  { print }
' "$SECRETS_FILE" > "$tmp"

install -m 600 "$tmp" "$SECRETS_FILE"

cd "$ROOT"
docker compose up -d n8n
sudo systemctl restart memo-bridge.service

echo "secrets reloaded"
