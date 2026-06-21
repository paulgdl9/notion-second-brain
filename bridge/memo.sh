# memo — capture rapide vers Inbox IA (webhook n8n)
# Localise ce fichier (sourcé depuis bash ou zsh) ; le .env du repo est un cran au-dessus.
_memo_self="${BASH_SOURCE[0]:-${(%):-%N}}"
_memo_dir="$(cd "$(dirname "$_memo_self")" 2>/dev/null && pwd)"
export N8N_SECRETS_FILE="${N8N_SECRETS_FILE:-${_memo_dir%/bridge}/.env}"

_memo_env_value() {
  local key="$1"
  grep -m1 "^${key}=" "$N8N_SECRETS_FILE" 2>/dev/null | cut -d= -f2- | tr -d '\n\r'
}

memo() {
  local src="${1:-Manual}" text resp capture_url
  local token="${N8N_CAPTURE_TOKEN:-}"
  if [ -z "$token" ] && [ -r "$N8N_SECRETS_FILE" ]; then
    token="$(_memo_env_value CAPTURE_TOKEN)"
  fi
  capture_url="${N8N_CAPTURE_URL:-$(_memo_env_value N8N_CAPTURE_URL)}"
  [ -n "$token" ] || { echo "memo: token webhook introuvable"; return 1; }
  [ -n "$capture_url" ] || { echo "memo: N8N_CAPTURE_URL introuvable"; return 1; }
  if [ -t 0 ]; then
    if command -v pbpaste >/dev/null 2>&1; then text="$(pbpaste)"
    elif command -v wl-paste >/dev/null 2>&1; then text="$(wl-paste)"
    elif command -v xclip >/dev/null 2>&1; then text="$(xclip -o -selection clipboard)"
    else echo "memo: pipe le texte → echo '...' | memo [source]"; return 1; fi
  else
    text="$(cat)"
  fi
  [ -n "$text" ] || { echo "memo: rien à envoyer"; return 1; }
  resp=$(printf '%s' "$text" \
    | python3 -c 'import json,sys; print(json.dumps({"source":sys.argv[1],"text":sys.stdin.read()}))' "$src" \
    | curl -sS --max-time 150 -X POST "$capture_url" \
        -H "Content-Type: application/json" \
        -H "X-Capture-Token: $token" -d @-)
  printf '%s' "$resp" | python3 -c '
import json,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw)
    print("✓ capturé : "+str(d.get("title","ok")) if d.get("ok") else "✗ échec : "+raw[:300])
except Exception:
    print("✗ réponse: "+(raw[:300] or "(vide)"))
'
}
