# n8n + memo-bridge second brain

A self-hosted objective-driven "second brain": an n8n stack plus a small Python bridge that
turns captures and an objectives database into a daily brief, all stored in Notion. It runs on
any Linux host with Docker (originally a Raspberry Pi).

Full operational documentation lives in [`docs/repo-overview.md`](docs/repo-overview.md).
The exact Notion databases and pages to create are described in
[`docs/notion-setup.md`](docs/notion-setup.md).

## Quick start

```bash
git clone <this-repo> second-brain && cd second-brain
./install.sh         # 1st run: creates .env + asks how you'll reach n8n
nano .env            # fill secrets, Notion IDs, Telegram, RSS feeds
./install.sh         # 2nd run: installs services, starts Docker, imports workflows
```

That's it — `install.sh` is idempotent, re-run it any time.

### How will you reach n8n? (the only real choice)

The first run asks **one question** and wires everything for you. **No public exposure is
required**: the daily brief only makes *outbound* calls to Notion and Claude. The only things that
ever need to *reach* n8n are your phone's capture shortcut and the editor UI — so pick the mode
that fits:

| Mode | Exposure | Pick it when |
|------|----------|--------------|
| **LAN only** | none | you capture / administer from your home network only |
| **Tailscale / VPN** *(recommended)* | no open ports | you want access from anywhere, zero exposure |
| **Cloudflare Tunnel** | public hostname | you want a public URL (needs a `CLOUDFLARED_TOKEN`) |

LAN and VPN modes never start the `cloudflared` container and never open a port on your router.
Switch later anytime: edit `ACCESS_MODE` (and the `N8N_*` vars) in `.env` and re-run `./install.sh`.

### What `install.sh` does

1. **Preflight** — checks Docker, `docker compose`, Python 3, `jq`; locates the `claude`/`codex` CLIs.
2. **`.env`** — creates it from `.env.example`, fills CLI paths, asks the access-mode question.
3. **systemd** — renders the bridge + watchdog units from `systemd/*.in` for your user and path.
4. **Docker** — starts n8n (plus `cloudflared` only in tunnel mode).
5. **Workflows** — imports + publishes them once `N8N_NOTION_CREDENTIAL_ID` is set.

### Prerequisites you install yourself

Docker Engine + the compose plugin, Python 3, `jq`, a [Notion integration](docs/notion-setup.md),
the `claude` CLI (and optionally `codex`) on your `PATH`, and — only for tunnel mode — a Cloudflare
tunnel token. Secrets live only in `.env` (never committed); `.env.example` is the template.

## Services

- `docker-compose.yml` runs `n8n` (and `cloudflared` only in tunnel mode — it sits behind a
  Compose profile). The n8n container reaches the host bridge via `host.docker.internal`
  (mapped through `extra_hosts`), so no gateway IP is hard-coded.
- `systemd/*.service.in` are templates rendered by `install.sh` for the current user/path
  (bridge + watchdog). Edit the templates, not the installed units under `/etc/systemd/system`.
- `bridge/memo-bridge.py` exposes `/summarize` (Haiku → Codex) and `/brief` (Sonnet → Codex) for n8n.
- `bridge/memo-summarize` is the Claude CLI wrapper used by `/summarize`.
- `bridge/memo.sh` sends quick captures to the public n8n webhook.

## Workflows

| Name | Purpose |
|------|---------|
| Capture - Notion (AI Inbox) | Authenticated manual capture |
| Daily Brief | Objective-driven daily synthesis |
| Automatic Watch - AI Inbox | Configurable RSS watch |
| Global Error Monitor | Failure alerts for every critical workflow |

Daily Brief is an **objective-driven copilot**: it reads the Objectives database (the compass) plus
open tasks from the Tasks database, AI Inbox captures, and the Notes journal. It proposes 1-3
tasks/day that get written back into the Tasks database, reviews still-open tasks, and uses tasks marked `Done`
in the last three days to propose the next logical step. It runs daily even with no new capture.
All personal context and behavioral rules come from the Notion page `System Context`. The bridge
contains no personal fallback and refuses contextual generation when that page is unavailable.

Automatic Watch runs before the Daily Brief. Feeds, keywords, age and volume limits are configured
through `WATCH_*` variables in `.env`; no personal source or topic is embedded in the workflow.

Both bridge routes use an LLM fallback: Claude → Codex CLI (OpenAI API key, no subscription
needed) → local fallback. Their responses include an `engine` field (`"claude"` / `"codex"` /
`"none"`). A **Telegram alert** fires automatically for a degraded Daily Brief.

Notion resources used by the **n8n RPi** integration: Daily Brief, Notes, `System Context`,
Objectives, Tasks, and AI Inbox. `System Context` is the runtime source for changing facts such
as employment, income, priorities, project progress, and copilot rules. Its ID is configured through
`NOTION_CONTEXT_PAGE_ID` in `.env` rather than embedded in the workflow export.

The host watchdog checks n8n health, cloudflared, memo-bridge, the Daily Brief heartbeat, and a
**public-URL canary** (an HTTP probe of `N8N_PUBLIC_URL/healthz` through Cloudflare, to catch a
tunnel that is up as a container but no longer routing) every five minutes. n8n's global error
workflow reports workflow and Notion failures independently.

Continuous integration ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) compiles the
Python sources, runs the bridge tests, validates every workflow JSON, and lints the shell scripts.

Docker images are pinned by version and digest. Healthchecks, process limits, and bounded JSON logs
are defined in `docker-compose.yml`; CPU and memory remain available dynamically.

## Rotate secrets

Edit `<repo>/.env`, then reload both consumers:

```bash
cd <repo>
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
