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
done

# 3) Import all workflows in one CLI process. Repeated n8n CLI startups consume enough resources
# to make the last import unreliable on small hosts such as a Raspberry Pi.
ordered=(
  global-error-monitor.workflow.json
  capture-notion.workflow.json
  automatic-watch.workflow.json
  task-lifecycle.workflow.json
  daily-brief.workflow.json
)
ordered_paths=()
for name in "${ordered[@]}"; do
  [ -f "$tmp/$name" ] || { echo "missing workflow file: $name" >&2; exit 1; }
  ordered_paths+=("$tmp/$name")
done
jq -s 'add' "${ordered_paths[@]}" > "$tmp/all-workflows.json"
docker cp "$tmp/all-workflows.json" n8n:/tmp/all-workflows.json
docker exec n8n n8n import:workflow --input=/tmp/all-workflows.json
docker exec n8n rm -f /tmp/all-workflows.json >/dev/null 2>&1 || true

workflow_ids=()
for name in "${ordered[@]}"; do
  workflow_id="$(jq -r '.[0].id' "$tmp/$name")"
  workflow_ids+=("$workflow_id")
  docker exec n8n n8n publish:workflow --id="$workflow_id"
done

wait_for_n8n() {
  local health
  for _ in $(seq 1 60); do
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' n8n 2>/dev/null || true)"
    [ "$health" = "healthy" ] && return 0
    sleep 1
  done
  echo "n8n did not become healthy after restart" >&2
  return 1
}

docker compose -f "$ROOT/docker-compose.yml" --project-directory "$ROOT" restart n8n
wait_for_n8n

is_published() {
  local workflow_id="$1" exported
  exported="$(docker exec n8n n8n export:workflow --id="$workflow_id" --pretty)"
  jq -e '.[0] | .active == true and .activeVersionId == .versionId' <<<"$exported" >/dev/null
}

# n8n imports deactivate workflows before publication. Verify the persisted state after the
# restart and retry once, so an interrupted CLI publication cannot silently disable a schedule.
retry=()
for workflow_id in "${workflow_ids[@]}"; do
  is_published "$workflow_id" || retry+=("$workflow_id")
done
if ((${#retry[@]})); then
  echo "retrying publication for: ${retry[*]}" >&2
  for workflow_id in "${retry[@]}"; do
    docker exec n8n n8n publish:workflow --id="$workflow_id"
  done
  docker compose -f "$ROOT/docker-compose.yml" --project-directory "$ROOT" restart n8n
  wait_for_n8n
fi
for workflow_id in "${workflow_ids[@]}"; do
  is_published "$workflow_id" || {
    echo "workflow is not active on its current version after import: $workflow_id" >&2
    exit 1
  }
done

echo "workflows imported and published"
