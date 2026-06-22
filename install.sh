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

# Upsert KEY=VALUE into .env (replace the line if present, append otherwise).
set_env() {
  local k="$1" v="$2" f="$REPO/.env"
  if grep -q "^$k=" "$f"; then sed -i "s#^$k=.*#$k=$v#" "$f"; else printf '%s=%s\n' "$k" "$v" >> "$f"; fi
}

# Ask once how n8n is reached, then persist ACCESS_MODE and the derived vars.
choose_access_mode() {
  local current; current="$(grep -m1 '^ACCESS_MODE=' "$REPO/.env" | cut -d= -f2-)"
  [ -n "$current" ] && { log "Access mode already set: $current"; return; }
  if [ ! -t 0 ]; then
    warn "No terminal; defaulting to LAN access. Edit ACCESS_MODE in .env to change."
    set_env ACCESS_MODE lan; set_env COMPOSE_PROFILES ""; set_env N8N_BIND 0.0.0.0; set_env N8N_PROTOCOL http
    return
  fi
  echo
  echo "How will you reach n8n from your devices?"
  echo "  1) LAN only          most private; only from your home network"
  echo "  2) Tailscale / VPN   private; from anywhere via your VPN  (recommended)"
  echo "  3) Cloudflare Tunnel public URL; needs a CLOUDFLARED_TOKEN"
  local choice; read -rp "Choice [1/2/3]: " choice
  case "$choice" in
    1) set_env ACCESS_MODE lan; set_env COMPOSE_PROFILES ""; set_env N8N_BIND 0.0.0.0; set_env N8N_PROTOCOL http
       warn "LAN: set N8N_HOST and N8N_PUBLIC_URL to http://<this-host-LAN-IP>:5678 in .env." ;;
    2) set_env ACCESS_MODE vpn; set_env COMPOSE_PROFILES ""; set_env N8N_BIND 0.0.0.0; set_env N8N_PROTOCOL http
       local ts=""; command -v tailscale >/dev/null 2>&1 && ts="$(tailscale ip -4 2>/dev/null | head -1)"
       warn "VPN: set N8N_HOST/N8N_PUBLIC_URL to http://<vpn-ip>:5678 in .env.${ts:+ (Tailscale IP detected: $ts)}" ;;
    3) set_env ACCESS_MODE tunnel; set_env COMPOSE_PROFILES tunnel; set_env N8N_BIND 127.0.0.1; set_env N8N_PROTOCOL https
       warn "Tunnel: set N8N_HOST/N8N_PUBLIC_URL to your public domain and CLOUDFLARED_TOKEN in .env." ;;
    *) die "invalid choice: '$choice' (expected 1, 2 or 3)" ;;
  esac
  log "Access mode saved to .env."
}

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

# --- 2. .env + access mode ------------------------------------------------
mkdir -p "$REPO/runtime" "$REPO/backups"
if [ ! -f "$REPO/.env" ]; then
  log "Creating .env from .env.example"
  cp "$REPO/.env.example" "$REPO/.env"
  chmod 600 "$REPO/.env"
  [ -n "$CLAUDE_BIN" ] && set_env CLAUDE_BIN "$CLAUDE_BIN"
  [ -n "$CODEX_BIN" ]  && set_env CODEX_BIN "$CODEX_BIN"
  choose_access_mode
  echo
  warn "First run done. Now edit $REPO/.env (secrets, Notion IDs, Telegram, feeds),"
  warn "then run ./install.sh again to install services and import workflows."
  exit 0
fi
chmod 600 "$REPO/.env"
choose_access_mode   # no-op if already chosen

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
log "Starting Docker stack"
profiles_val="$(grep -m1 '^COMPOSE_PROFILES=' "$REPO/.env" | cut -d= -f2- | tr -d '\r\n')"
if [ "$profiles_val" = "tunnel" ] && ! grep -qE '^CLOUDFLARED_TOKEN=.+' "$REPO/.env"; then
  warn "tunnel mode selected but CLOUDFLARED_TOKEN looks empty — the tunnel will not connect."
fi
COMPOSE_PROFILES="$profiles_val" \
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
