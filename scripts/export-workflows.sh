#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/SSD/n8n}"
ENV_FILE="$ROOT/.env"
credential_id="$(grep -m1 '^N8N_NOTION_CREDENTIAL_ID=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r\n')"
[ -n "$credential_id" ] || { echo "N8N_NOTION_CREDENTIAL_ID is missing" >&2; exit 1; }

export_one() {
  local id="$1" output="$2" tmp
  tmp="$(mktemp)"
  docker exec n8n n8n export:workflow --id="$id" --pretty > "$tmp"
  jq --arg credential "$credential_id" '
    map(
      del(.shared, .createdAt, .updatedAt, .versionMetadata)
      | walk(if type == "string" and . == $credential then "__NOTION_CREDENTIAL_ID__" else . end)
    )
  ' "$tmp" > "$output"
  rm -f "$tmp"
}

export_one DbqnFl5IAG014bRK "$ROOT/workflows/capture-notion.workflow.json"
export_one hB7QvnPqejSe6LtU "$ROOT/workflows/daily-brief.workflow.json"
export_one vRssAutoIA062026 "$ROOT/workflows/automatic-watch.workflow.json"
export_one globalErrorMonitor "$ROOT/workflows/global-error-monitor.workflow.json"

echo "sanitized workflow exports updated"
