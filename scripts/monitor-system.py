#!/usr/bin/env python3
import json
import os
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(os.environ.get("N8N_ROOT", "/SSD/n8n"))
ENV_FILE = ROOT / ".env"
STATE_DIR = Path(os.environ.get("MONITOR_STATE_DIR", str(ROOT / "runtime")))
STATE_FILE = STATE_DIR / "monitor-state.json"
BRIEF_HEARTBEAT = STATE_DIR / "brief-heartbeat.json"


def load_env():
    values = {}
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def command_ok(args):
    try:
        return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=10).returncode == 0
    except Exception:
        return False


def container_ok(name, require_health=False):
    try:
        out = subprocess.check_output(
            ["docker", "inspect", "-f", "{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}", name],
            text=True, stderr=subprocess.DEVNULL, timeout=10).strip().split()
        return bool(out and out[0] == "true" and (not require_health or out[1:] == ["healthy"]))
    except Exception:
        return False


def bridge_ok(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/health" % port, timeout=4) as response:
            return response.status == 200 and json.load(response).get("ok") is True
    except Exception:
        return False


def brief_ok(expected_by):
    now = datetime.now()
    hour, minute = (int(x) for x in expected_by.split(":", 1))
    if (now.hour, now.minute) < (hour, minute):
        return True
    try:
        data = json.loads(BRIEF_HEARTBEAT.read_text(encoding="utf-8"))
        return data.get("brief_date") == now.strftime("%d/%m/%Y")
    except Exception:
        return False


def telegram(env, message):
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("monitor: Telegram configuration missing", file=sys.stderr)
        return False
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
    try:
        request = urllib.request.Request(
            "https://api.telegram.org/bot%s/sendMessage" % token, data=body, method="POST")
        with urllib.request.urlopen(request, timeout=12) as response:
            return response.status == 200
    except Exception as exc:
        print("monitor: Telegram send failed: %s" % exc, file=sys.stderr)
        return False


def main():
    env = load_env()
    checks = {
        "n8n": container_ok("n8n", require_health=True),
        "cloudflared": container_ok("cloudflared"),
        "memo-bridge": bridge_ok(env.get("MEMO_PORT", "8088")),
        "daily-brief": brief_ok(env.get("BRIEF_EXPECTED_BY", "08:15")),
    }
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        previous = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        previous = {}
    changed_down = [name for name, ok in checks.items() if not ok and previous.get(name) is not False]
    recovered = [name for name, ok in checks.items() if ok and previous.get(name) is False]
    host = socket.gethostname()
    if changed_down:
        telegram(env, "ALERTE système (%s)\nÉchec: %s" % (host, ", ".join(changed_down)))
    if recovered:
        telegram(env, "RÉTABLI système (%s)\nOK: %s" % (host, ", ".join(recovered)))
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(checks, sort_keys=True), encoding="utf-8")
    os.replace(tmp, STATE_FILE)
    return 1 if any(not ok for ok in checks.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
