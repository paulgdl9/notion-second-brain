#!/usr/bin/env bash
# One-shot installer for the n8n + memo-bridge second-brain stack.
# Idempotent and safe to re-run. Locates the repo from its own path, so it can
# be run from anywhere. Steps: preflight -> .env -> systemd units -> docker -> workflows.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. Preflight ---------------------------------------------------------
log "Checking prerequisites"
need() { command -v "$1" >/dev/null 2>&1 || die "missing required command: $1 ($2)"; }
need docker "install Docker Engine"
docker compose version >/dev/null 2>&1 || die "missing the 'docker compose' plugin"
need python3 "install Python 3"
need jq "install jq"

CLAUDE_BIN="$(command -v claude || true)"
CODEX_BIN="$(command -v codex || true)"
[ -n "$CLAUDE_BIN" ] || warn "claude CLI not found on PATH — the bridge will fall back to Codex/local"
[ -n "$CODEX_BIN" ]  || warn "codex CLI not found on PATH — no LLM fallback available"

# --- 2. .env --------------------------------------------------------------
if [ ! -f "$REPO/.env" ]; then
  log "Creating .env from .env.example"
  cp "$REPO/.env.example" "$REPO/.env"
  chmod 600 "$REPO/.env"
  [ -n "$CLAUDE_BIN" ] && sed -i "s#^CLAUDE_BIN=.*#CLAUDE_BIN=$CLAUDE_BIN#" "$REPO/.env"
  [ -n "$CODEX_BIN" ]  && sed -i "s#^CODEX_BIN=.*#CODEX_BIN=$CODEX_BIN#"  "$REPO/.env"
  warn "Edit $REPO/.env (secrets, Notion IDs, Telegram, feeds), then re-run this script."
else
  log ".env already present — leaving it untouched"
fi
chmod 600 "$REPO/.env"
mkdir -p "$REPO/runtime" "$REPO/backups"

# --- 3. systemd units (bridge + watchdog) ---------------------------------
if command -v systemctl >/dev/null 2>&1; then
  log "Installing systemd units"
  RUN_USER="${SUDO_USER:-$USER}"
  RUN_GROUP="$(id -gn "$RUN_USER")"
  RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
  PYTHON_BIN="$(command -v python3)"
  render_unit() {
    sed -e "s#@USER@#$RUN_USER#g" -e "s#@GROUP@#$RUN_GROUP#g" \
        -e "s#@HOME@#$RUN_HOME#g" -e "s#@REPO@#$REPO#g" \
        -e "s#@PYTHON@#$PYTHON_BIN#g" "$1" | sudo tee "$2" >/dev/null
  }
  render_unit "$REPO/systemd/memo-bridge.service.in" /etc/systemd/system/memo-bridge.service
  render_unit "$REPO/systemd/n8n-monitor.service.in" /etc/systemd/system/n8n-monitor.service
  sudo cp "$REPO/systemd/n8n-monitor.timer" /etc/systemd/system/n8n-monitor.timer
  sudo systemctl daemon-reload
  sudo systemctl enable --now memo-bridge.service
  sudo systemctl enable --now n8n-monitor.timer
else
  warn "systemctl not found — start the bridge and watchdog manually"
fi

# --- 4. Docker stack ------------------------------------------------------
log "Starting Docker stack (n8n + cloudflared)"
docker compose -f "$REPO/docker-compose.yml" --project-directory "$REPO" up -d

# --- 5. Workflows ---------------------------------------------------------
cred="$(grep -m1 '^N8N_NOTION_CREDENTIAL_ID=' "$REPO/.env" | cut -d= -f2- | tr -d '\r\n')"
if [ -n "$cred" ]; then
  log "Importing workflows"
  "$REPO/scripts/import-workflows.sh"
  log "Install complete."
else
  warn "N8N_NOTION_CREDENTIAL_ID is empty — skipping workflow import."
  warn "Create the Notion credential in n8n, set its id in .env, then run: scripts/import-workflows.sh"
fi
