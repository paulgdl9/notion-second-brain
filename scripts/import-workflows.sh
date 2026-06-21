#!/usr/bin/env bash
# Import every versioned workflow into the running n8n container.
#   1. validate all JSON up front (never start importing a broken set)
#   2. back up the workflows currently live in n8n (manual rollback if needed)
#   3. substitute the Notion credential placeholder from .env, then import + publish
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="$ROOT/.env"
credential_id="$(grep -m1 '^N8N_NOTION_CREDENTIAL_ID=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r\n')"
[ -n "$credential_id" ] || { echo "N8N_NOTION_CREDENTIAL_ID is missing in $ENV_FILE" >&2; exit 1; }

# 1) Validate every workflow file before touching n8n.
for source in "$ROOT"/workflows/*.json; do
  jq empty "$source" 2>/dev/null || { echo "invalid JSON: $source" >&2; exit 1; }
done

# 2) Back up the workflows currently live in n8n (best effort, non-fatal).
backup_dir="$ROOT/backups/pre-import-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
if docker exec n8n n8n export:workflow --all --output=/tmp/n8n-pre-import.json >/dev/null 2>&1; then
  docker cp "n8n:/tmp/n8n-pre-import.json" "$backup_dir/workflows.json" >/dev/null 2>&1 || true
  docker exec n8n rm -f /tmp/n8n-pre-import.json >/dev/null 2>&1 || true
  echo "backed up current workflows to $backup_dir"
else
  echo "warning: could not back up current workflows (continuing)" >&2
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

for source in "$ROOT"/workflows/*.json; do
  target="$tmp/$(basename "$source")"
  sed "s/__NOTION_CREDENTIAL_ID__/$credential_id/g" "$source" > "$target"
  docker cp "$target" "n8n:/tmp/$(basename "$target")"
done

# 3) The global error workflow must exist before the workflows that reference it.
ordered=(
  global-error-monitor.workflow.json
  capture-notion.workflow.json
  automatic-watch.workflow.json
  daily-brief.workflow.json
)
for name in "${ordered[@]}"; do
  [ -f "$tmp/$name" ] || { echo "missing workflow file: $name" >&2; exit 1; }
  docker exec n8n n8n import:workflow --input="/tmp/$name"
  workflow_id="$(jq -r '.[0].id' "$tmp/$name")"
  docker exec n8n n8n publish:workflow --id="$workflow_id"
  docker exec n8n rm -f "/tmp/$name" >/dev/null 2>&1 || true
done

docker compose -f "$ROOT/docker-compose.yml" --project-directory "$ROOT" restart n8n
echo "workflows imported and published"
