# n8n Raspberry Pi repository

This repository documents and versions the n8n configuration hosted on a Raspberry Pi in
`<repo>`. Git contains the system definition; secrets and runtime state remain on the host.

## Architecture

The system has four main components:

- `n8n`, launched by Docker Compose, runs the workflows and is exposed through `N8N_PUBLIC_URL`.
- `cloudflared`, launched only with the Compose `tunnel` profile. LAN and VPN modes do not start it
  or open a router port. The Daily Brief only needs outbound Notion and LLM calls; public access is
  used only by the capture webhook and editor.
- `memo-bridge`, launched by systemd, exposes a local API that summarizes captures and generates
  the Daily Brief through Claude or Codex.
- Notion, which stores the AI Inbox, Objectives, Tasks, Notes, System Context, and Daily Brief.

### Capture flow

```text
memo.sh / iOS Shortcut / curl
  -> ${N8N_CAPTURE_URL}
  -> Capture - Notion (AI Inbox)
  -> memo-bridge /summarize
  -> Notion AI Inbox
```

### Automatic Watch flow

```text
Every day at 6:10
  -> read URLs already stored in the AI Inbox
  -> read feeds configured through WATCH_RSS_FEEDS
  -> rank with WATCH_KEYWORDS and WATCH_* limits
  -> deduplicate and limit volume
  -> memo-bridge /summarize
  -> Notion AI Inbox (Status=Inbox)
```

The selection is intentionally small so the Daily Brief remains useful. Feed sources, keywords,
age, and volume are configured in `.env`.

### Daily Brief flow

The Daily Brief is an objective-driven copilot. Objectives drive it; captures and the journal are
supporting material. It runs every day even when the AI Inbox is empty, proposes up to three new
tasks, reviews open tasks, and uses recently completed tasks as progress signals.

```text
Every day at 7:00
  -> AI Inbox - pages (Notion getAll; alwaysOutputData)
  -> Prepare (Status=Inbox; always returns one item)
  -> Brief: existing blocks
  -> Skip existing brief (stop here when today's brief already exists)
  -> Notes - blocks
  -> Prepare Notes rollover
       |-> write Today under yesterday in Journal -> clear Today
       \-> no notes -> continue
  -> System context - blocks
  -> Active objectives
  -> Tasks - all
  -> Enrich payload
  -> memo-bridge /brief (Claude, then Codex)
  -> Brief fallback if Claude fails
       |-> Build write payload
       |     -> Notion: write brief
       |          |-> IDs to process -> Mark Briefed
       |          \-> Tasks to create -> Create tasks
       \-> Detect degradation -> Telegram alert

Parallel branch from Tasks - all:
  -> Stale tasks (older than seven days)
       -> Abandon tasks (Status=Abandoned)
```

Notion's append-children API cannot prepend, but accepts `after: <block_id>`. The Daily Brief page
must keep a permanent first block. New briefs are inserted after it so the newest brief stays at
the top. If the first block is deleted, the workflow falls back to appending at the bottom. Before
reading context or calling an LLM, the workflow scans the page headings for the current date and
stops when that day's brief already exists.

The Notes rollover copies non-empty blocks from `Today` under yesterday's Journal heading, writes a
`Daily notes` marker, and only then archives the original blocks. Empty spacer blocks are cleared but
not copied. If clearing fails after the write, the next run sees the marker and resumes cleanup
without duplicating content. Unsupported or nested blocks stop the workflow instead of being lost.

### Task lifecycle flow

```text
Every 10 minutes
  -> read every row in Tasks
  -> Status=Done and Done on empty: set Done on
  -> Status!=Done and Done on present: clear Done on
```

This invariant makes reopening and completing a task again produce a fresh completion date. The
Daily Brief also treats a just-completed task without a date as completed now, covering the short
window before the lifecycle workflow runs.

## Important files

- `install.sh`: idempotent preflight, configuration, service installation, and workflow import.
- `docker-compose.yml`: n8n and the optional Cloudflare Tunnel.
- `.env.example`: safe template for runtime variables.
- `<repo>/.env`: real secrets and configuration; never commit it.
- `bridge/memo-bridge.py`: local `/summarize`, `/brief`, `/weekly`, and heartbeat API.
- `prompts/weekly-review.md`: generic, versioned Weekly Review instructions.
- `bridge/memo-summarize`: Claude CLI wrapper for `/summarize`.
- `bridge/memo.sh`: command-line capture helper.
- `systemd/*.service.in`: service templates rendered by `install.sh`.
- `scripts/monitor-system.py`: service, public canary, and heartbeat watchdog.
- `scripts/{import,export}-workflows.sh`: validated workflow synchronization.
- `docs/notion-setup.md`: exact Notion schema.
- `workflows/`: sanitized n8n workflow exports.
- `backups/`: ignored local workflow backups.

## Secret source of truth

`<repo>/.env` is the only active source of secrets. It is read by Docker Compose, the n8n
container, `memo-bridge.service`, `bridge/memo.sh`, and `scripts/monitor-system.py`. Do not keep
active token copies under older paths such as `secrets/common.env`, `bridge/memo-bridge.env`, or
`bridge/webhook-token.txt`.

### `MEMO_TOKEN`

Internal bearer token between n8n and `memo-bridge`. It protects:

- `POST /summarize`
- `POST /brief`
- `POST /weekly`
- `POST /heartbeat/brief`
- `POST /heartbeat/capture`

An incorrect value prevents n8n HTTP nodes from reaching the bridge.

### `CAPTURE_TOKEN`

Authentication token for the public capture webhook. External clients send it as:

```text
X-Capture-Token: <CAPTURE_TOKEN>
```

The capture workflow returns HTTP 401 when the header does not match `$env.CAPTURE_TOKEN`.

### `MEMO_PORT`

Local port used by `memo-bridge`; the default is `8088`. n8n reaches it through
`MEMO_BRIDGE_URL`, so workflow exports contain no host-specific address.

### `CLOUDFLARED_TOKEN`

Cloudflare Tunnel token used only by the `cloudflared` container. An invalid token affects public
access but does not stop local n8n execution or outbound Daily Brief calls.

## Operations

### Rotate secrets

Edit `<repo>/.env`, then reload consumers:

```bash
cd <repo>
docker compose up -d n8n
sudo systemctl restart memo-bridge.service
```

Quick verification:

```bash
systemctl is-active memo-bridge.service
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^(n8n|cloudflared) '
```

Test webhook rejection:

```bash
. ./.env
curl -sS -i -X POST "$N8N_CAPTURE_URL" \
  -H 'Content-Type: application/json' \
  -d '{"source":"Manual","text":"unauthorized check"}'
```

Test the local bridge:

```bash
. ./.env
curl -sS -X POST http://127.0.0.1:${MEMO_PORT}/summarize \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${MEMO_TOKEN}" \
  -d '{"source":"Manual","text":"health check"}'
```

### Export workflows

Versioned exports must come from the current n8n instance:

```bash
scripts/export-workflows.sh
```

The script removes owner metadata and replaces the local Notion credential ID with
`__NOTION_CREDENTIAL_ID__`. It writes atomically so a failed `jq` transformation cannot truncate
an existing export.

### Import workflows

```bash
scripts/import-workflows.sh
```

The import script validates every JSON file before changing n8n, creates a best-effort backup,
substitutes `N8N_NOTION_CREDENTIAL_ID`, imports the Global Error Monitor first, publishes every
workflow, and restarts n8n.

n8n schedules and triggers run the published `activeVersionId`. Any API or MCP update creates a
draft version and must be followed by a publish operation.

### Git checks

Before a commit:

```bash
git status --short
git diff --cached --name-status
git grep --cached -n -E '(Bearer [0-9a-f]{20,}|MEMO_TOKEN=[0-9a-f]|CAPTURE_TOKEN=[0-9a-f]|CLOUDFLARED_TOKEN=eyJhIjoi|eyJhIjoi)' || true
```

Never commit `.env`, `backups/`, raw exports containing credentials, or generated runtime files.

## Installation

`./install.sh` performs the preflight, creates `.env` from `.env.example`, renders systemd units
for the current user and repository path, starts Docker, and imports workflows once
`N8N_NOTION_CREDENTIAL_ID` is configured.

The systemd files under `systemd/` are templates. Edit them and rerun `install.sh`; do not edit the
rendered units under `/etc/systemd/system`. No machine-specific path is hard-coded.

## Notion sharing

Every resource must be explicitly shared with the Notion integration configured in n8n:

| Resource | Variable | Purpose |
|----------|----------|---------|
| Daily Brief | `NOTION_DAILY_BRIEF_PAGE_ID` | brief destination |
| Notes | `NOTION_NOTES_PAGE_ID` | recent journal and todos |
| Objectives | `NOTION_OBJECTIVES_DATABASE_ID` | active objectives |
| Tasks | `NOTION_TASKS_DATABASE_ID` | task feedback loop |
| System Context | `NOTION_CONTEXT_PAGE_ID` | profile, priorities, and rules |
| AI Inbox | `NOTION_INBOX_DATABASE_ID` | manual and automatic captures |
| Library (optional) | `NOTION_LIBRARY_DATABASE_ID` | weekly Readwise/library evidence |

Resources created through another Notion integration still need to be shared with the n8n
integration, otherwise Notion nodes return 404.

System Context is the sole runtime source for personal profile and behavioral rules. Objectives
live in the Objectives database and recent journal entries live on the Notes page. When System
Context cannot be read, the bridge refuses contextual generation and the workflow sends an alert.

## Bridge engines

The `/brief` route uses this fallback chain:

1. Claude (`claude-sonnet-4-6`, `claude -p --strict-mcp-config`).
2. Codex (`codex exec --sandbox read-only --skip-git-repo-check`).
3. `none`, which returns 502 and lets n8n build its minimal local fallback.

`--strict-mcp-config` is required. It disables MCP servers and keeps Claude limited to the supplied
prompt. The response exposes `engine` and `context_source`:

```text
{brief, blocks, tasks, count, engine, context_source}
```

`/summarize` follows the same Claude-to-Codex chain, then preserves the capture through a local
fallback. Generation routes report `claude`, `codex`, or `none` in the `engine` field.

## Weekly Review contract

Every Sunday at 19:00, `Weekly Review` reads System Context, the week's Daily Briefs, dated Journal
entries and todos, Objectives, Tasks, and the optional Library database. It calls `/weekly`, then
inserts the result after the permanent first block of the Daily Brief page. A matching
week heading stops a retry before any additional generation.

The evidence contract is deliberately stricter than the Daily Brief: a task counts as execution
only when `Status=Done` and `Done on` falls within the review period; Journal entries are evidence;
Daily Briefs remain intentions. The model proposes exact objective edits but the workflow never
changes Objectives, Notes, Tasks, or System Context. `WEEKLY_LANGUAGE` controls the output language.

## Daily Brief contract

Input fields:

- `system_context`: System Context page blocks, including copilot rules.
- `objectives`: Objectives rows with `Status=Active`.
- `open_tasks`: Tasks rows with `Status=To do` and less than seven days old.
- `completed_tasks`: tasks set to `Done` in the last three days, newest first, at most ten.
- `items`: current AI Inbox captures with `Status=Inbox`.
- `context`: `Today`, `Journal`, and `Todo` sections from Notes.

The bridge outputs Markdown, Notion blocks, and parsed task objects using the exact contract
`{title, area, why}`. `extract_tasks()` parses this section:

```text
### ✅ Today's tasks
- **[Area]** Actionable title — why
```

The full brief structure is:

```text
## 🗓️ Daily Brief — DD/MM/YYYY
### 📌 Follow-up
### 🔗 Connections
### ⚡ Contradictions / blind spots
### ✅ Today's tasks
### 🎓 To learn
### ❓ Question to explore
```

## Observability

- Global Error Monitor reports workflow, node, error, and execution details to Telegram.
- Notion read failures become observable errors instead of silently producing empty results.
- Capture and Daily Brief workflows write heartbeats through the bridge.
- `n8n-monitor.timer` checks n8n, cloudflared when enabled, memo-bridge, the public URL canary, and
  the expected Daily Brief heartbeat every five minutes.
- Watchdog alerts are deduplicated and sent on failure and recovery transitions.
- The canary sends a normal browser User-Agent because Cloudflare may reject urllib's default one.

## Reproducibility and safeguards

n8n and cloudflared images are pinned by version and digest. Docker logs rotate and process counts
are limited to avoid exhausting the host or disk. CPU and memory remain dynamically available.
CI compiles Python, runs bridge tests, executes embedded n8n Code-node JavaScript against fixtures,
validates workflow JSON, and lints shell scripts.
