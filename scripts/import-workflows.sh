#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/SSD/n8n}"
ENV_FILE="$ROOT/.env"
credential_id="$(grep -m1 '^N8N_NOTION_CREDENTIAL_ID=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r\n')"
[ -n "$credential_id" ] || { echo "N8N_NOTION_CREDENTIAL_ID is missing" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

for source in "$ROOT"/workflows/*.json; do
  target="$tmp/$(basename "$source")"
  sed "s/__NOTION_CREDENTIAL_ID__/$credential_id/g" "$source" > "$target"
  docker cp "$target" "n8n:/tmp/$(basename "$target")"
done

# The referenced error workflow must exist before importing dependent workflows.
ordered=(
  global-error-monitor.workflow.json
  capture-notion.workflow.json
  automatic-watch.workflow.json
  daily-brief.workflow.json
)
for name in "${ordered[@]}"; do
  docker exec n8n n8n import:workflow --input="/tmp/$name"
  workflow_id="$(jq -r '.[0].id' "$tmp/$name")"
  docker exec n8n n8n publish:workflow --id="$workflow_id"
done

docker compose -f "$ROOT/docker-compose.yml" --project-directory "$ROOT" restart n8n
