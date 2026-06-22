# Notion setup

The stack reads from and writes to a small set of Notion databases and pages. You can
either **duplicate the public template** (fastest) or **recreate the schema by hand** using the
tables below. Either way, every database and page must be **shared with your n8n Notion
integration**, and their IDs copied into `.env`.

## Option A — duplicate the template (recommended)

1. Open the template: `TODO: <public Notion template URL>` and click **Duplicate**.
2. Share each duplicated database/page with your integration (see "Sharing" below).
3. Copy each ID into `.env` (see "IDs" below).

> The template URL is a placeholder until published. Until then, use Option B.

## Option B — recreate the schema by hand

Property **names, types, and select options must match exactly** — they are referenced
literally by the workflows. Select options are not created automatically; add them yourself.

### Inbox database — `NOTION_INBOX_DATABASE_ID`

Captured items (manual captures + automatic RSS watch). One title + the following properties:

| Property      | Type         | Options / notes                                  |
|---------------|--------------|--------------------------------------------------|
| *(title)*     | Title        | the database title column (e.g. `Name`)          |
| Source        | Select       | `Twitter`, `Mail`, `AI`, `Article`, `Manual`     |
| URL           | URL          |                                                  |
| Summary       | Text         |                                                  |
| Insight       | Text         |                                                  |
| Next Action   | Text         |                                                  |
| Area          | Select       | must match the values of `MEMO_AREAS` in `.env`  |
| Tags          | Multi-select |                                                  |
| Importance    | Number       | 1–5                                              |
| Raw Content   | Text         |                                                  |
| Captured At   | Date         |                                                  |
| Status        | Select       | `Inbox`, `Briefed`, `Archived`                   |
| Briefed At    | Date         |                                                  |

### Objectives database — `NOTION_OBJECTIVES_DATABASE_ID`

The compass that drives the Daily Brief (read-only for the stack).

| Property        | Type   | Options / notes                                |
|-----------------|--------|------------------------------------------------|
| Name          | Title  |                                                |
| Area          | Select | must match `MEMO_AREAS`                         |
| Status        | Select | `Active`, `Paused`, `Achieved`                  |
| Priority      | Select | `High`, `Medium`, `Low`                         |
| Current state | Text   |                                                |
| Next step     | Text   |                                                |
| Horizon       | Text   |                                                |

Only objectives with `Status = Active` are sent to the brief.

### Tasks database — `NOTION_TASKS_DATABASE_ID`

The brief proposes 1–3 tasks/day here; still-open and recently-completed tasks feed back in.

| Property    | Type   | Options / notes                                   |
|-------------|--------|---------------------------------------------------|
| Task        | Title  |                                                   |
| Status      | Select | `To do`, `Done`, `Abandoned`                      |
| Area        | Select | must match `MEMO_AREAS`                           |
| Why         | Text   | why this task serves an objective                 |
| Feedback    | Text   | result or blocker you write back; read by the brief |
| Source      | Select | `Brief`, `Manual`                                 |
| Proposed on | Date   | tasks older than ~7 days with `To do` are auto-abandoned |
| Done on     | Date   | maintained automatically from `Status` every 10 minutes |

### Pages

| Page             | `.env` variable             | Role                                                                 |
|------------------|-----------------------------|----------------------------------------------------------------------|
| Daily Brief      | `NOTION_DAILY_BRIEF_PAGE_ID`| Brief output. Keep a permanent first block as a header — new briefs are inserted right after it (most recent on top). |
| Notes            | `NOTION_NOTES_PAGE_ID`      | Journal. Recognized `heading_2`/`heading_1` sections: `Today`, `Journal`, and `Todo`/`✅`. The Daily Brief moves `Today` under yesterday's Journal date, then clears it. An `Archive`/`🗄` heading ends parsing. |
| System Context   | `NOTION_CONTEXT_PAGE_ID`    | Free text read each morning as the brief's system context (who you are, projects, priorities, copilot rules). No personal data lives in the code. |

The `Task Lifecycle (Done on)` workflow sets `Done on` when a task reaches `Done`, clears it when
the task is reopened or abandoned, and sets a fresh completion date if it is completed again.

The Notes rollover runs only when a new Daily Brief is due. It writes a `Daily notes` marker under
yesterday's Journal date before clearing `Today`; retries detect that marker and never duplicate the
archived notes.

## Sharing

For each database and page above: open it in Notion → `•••` → **Connections** →
add your n8n integration. Databases created through a *different* Notion integration must
still be shared explicitly with the n8n one, or the n8n nodes return `404`.

## IDs

Copy the ID from each Notion URL into `.env`. The ID is the 32-character hex string in the URL
(`https://www.notion.so/<workspace>/<title>-<ID>`):

```
NOTION_INBOX_DATABASE_ID=
NOTION_DAILY_BRIEF_PAGE_ID=
NOTION_NOTES_PAGE_ID=
NOTION_CONTEXT_PAGE_ID=
NOTION_OBJECTIVES_DATABASE_ID=
NOTION_TASKS_DATABASE_ID=
N8N_NOTION_CREDENTIAL_ID=   # the id of the Notion credential you create inside n8n
```

`N8N_NOTION_CREDENTIAL_ID` is **not** a Notion ID: it is the id of the Notion credential you
create in the n8n UI (Credentials → Notion API). `scripts/import-workflows.sh` substitutes it
into the workflow exports at import time.
