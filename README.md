# n8n Raspberry Pi setup

This repository tracks the n8n runtime configuration and workflow exports for `/SSD/n8n`.

Full operational documentation lives in [`docs/repo-overview.md`](docs/repo-overview.md).

Secrets are centralized on the Raspberry Pi in:

```bash
/SSD/n8n/.env
```

Do not commit the real file. Use `.env.example` as the template.

## Services

- `docker-compose.yml` runs `n8n` and `cloudflared`.
- `systemd/memo-bridge.service` runs the local Python bridge.
- `bridge/memo-bridge.py` exposes `/summarize` (Haiku → Codex) and `/brief` (Sonnet → Codex) for n8n.
- `bridge/memo-summarize` is the Claude CLI wrapper used by `/summarize`.
- `bridge/memo.sh` sends quick captures to the public n8n webhook.

## Workflows

| Name | Purpose |
|------|---------|
| Capture → Notion | Authenticated manual capture |
| Daily Brief | Objective-driven daily synthesis |
| Veille automatique | Configurable RSS watch |
| Monitoring — erreurs globales | Failure alerts for every critical workflow |

Daily Brief is an **objective-driven copilot**: it reads the 🎯 Objectifs DB (the compass) plus open
tasks from the ✅ Tâches DB, the Inbox IA captures, and the Notes journal. It proposes 1-3 tasks/day
that get written back into the ✅ Tâches DB, reviews still-open tasks, and uses tasks marked `Fait`
in the last three days to propose the next logical step. It runs daily even with no new capture.
All personal context and behavioral rules come from the Notion page `Contexte Système`. The bridge
contains no personal fallback and refuses contextual generation when that page is unavailable.

Automatic Watch runs before the Daily Brief. Feeds, keywords, age and volume limits are configured
through `WATCH_*` variables in `.env`; no personal source or topic is embedded in the workflow.

Both bridge routes use an LLM fallback: Claude → Codex CLI (OpenAI API key, no subscription
needed) → local fallback. Their responses include an `engine` field (`"claude"` / `"codex"` /
`"none"`). A **Telegram alert** fires automatically for a degraded Daily Brief.

Notion resources used by the **n8n RPi** integration: Daily Brief, Notes, `Contexte Système`,
🎯 Objectifs DB, and ✅ Tâches DB. `Contexte Système` is the runtime source for changing facts such
as employment, income, priorities, project progress, and copilot rules. Its ID is configured through
`NOTION_CONTEXT_PAGE_ID` in `.env` rather than embedded in the workflow export.

The host watchdog checks n8n health, cloudflared, memo-bridge, and the Daily Brief heartbeat every
five minutes. n8n's global error workflow reports workflow and Notion failures independently.

Docker images are pinned by version and digest. Healthchecks, process limits, and bounded JSON logs
are defined in `docker-compose.yml`; CPU and memory remain available dynamically.

## Rotate secrets

Edit `/SSD/n8n/.env`, then reload both consumers:

```bash
cd /SSD/n8n
docker compose up -d n8n
sudo systemctl restart memo-bridge.service
```

The tracked compose file reads `CLOUDFLARED_TOKEN` via Docker Compose interpolation and injects the same `.env` into the n8n container.

## Export workflows

```bash
scripts/export-workflows.sh
```

The export script removes ownership metadata and replaces the local Notion credential ID with a
neutral placeholder. `scripts/import-workflows.sh` reverses that substitution from `.env`, imports
the global error workflow first, publishes every workflow, and restarts n8n.

Always scan exports before committing:

```bash
rg -n -i '(Bearer [0-9a-f]{20,}|MEMO_TOKEN=|CAPTURE_TOKEN=|CLOUDFLARED_TOKEN=|TELEGRAM_BOT_TOKEN=|eyJhIjoi)' .
```
