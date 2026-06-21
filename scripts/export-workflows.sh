#!/usr/bin/env bash
# Re-export the live workflows into the repo, stripping owner metadata and the
# Notion credential id. Each workflow's n8n id is read from the committed JSON,
# so there are no hard-coded ids. Writes atomically: a jq failure never
# truncates an existing file.
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="$ROOT/.env"
credential_id="$(grep -m1 '^N8N_NOTION_CREDENTIAL_ID=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r\n')"
[ -n "$credential_id" ] || { echo "N8N_NOTION_CREDENTIAL_ID is missing in $ENV_FILE" >&2; exit 1; }

export_one() {
  local output="$1" id raw clean
  id="$(jq -r '.[0].id' "$output")"
  [ -n "$id" ] && [ "$id" != "null" ] || { echo "no workflow id in $output" >&2; return 1; }
  raw="$(mktemp)"; clean="$(mktemp)"
  docker exec n8n n8n export:workflow --id="$id" --pretty > "$raw"
  jq --arg credential "$credential_id" '
    map(
      del(.shared, .createdAt, .updatedAt, .versionMetadata)
      | walk(if type == "string" and . == $credential then "__NOTION_CREDENTIAL_ID__" else . end)
    )
  ' "$raw" > "$clean"
  mv "$clean" "$output"          # atomic: only overwrites once jq succeeded
  rm -f "$raw"
}

for f in "$ROOT"/workflows/*.json; do
  export_one "$f"
done

echo "sanitized workflow exports updated"
