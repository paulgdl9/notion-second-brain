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
| Source        | Select       | `Twitter`, `Mail`, `IA`, `Article`, `Manual`     |
| URL           | URL          |                                                  |
| Summary       | Text         |                                                  |
| Insight       | Text         |                                                  |
| Next Action   | Text         |                                                  |
| Area          | Select       | must match the values of `MEMO_AREAS` in `.env`  |
| Tags          | Multi-select |                                                  |
| Importance    | Number       | 1–5                                              |
| Raw Content   | Text         |                                                  |
| Captured At   | Date         |                                                  |
| Status        | Select       | `Inbox`, `Briefed`, `Archivé`                    |
| Briefed At    | Date         |                                                  |

### Objectives database — `NOTION_OBJECTIVES_DATABASE_ID`

The compass that drives the Daily Brief (read-only for the stack).

| Property        | Type   | Options / notes                                |
|-----------------|--------|------------------------------------------------|
| Nom             | Title  |                                                |
| Domaine         | Select | must match `MEMO_AREAS`                         |
| Statut          | Select | `Actif`, `En pause`, `Atteint`                 |
| Priorité        | Select | `Haute`, `Moyenne`, `Basse`                    |
| État actuel     | Text   |                                                |
| Prochaine étape | Text   |                                                |
| Horizon         | Text   |                                                |

Only objectives with `Statut = Actif` are sent to the brief.

### Tasks database — `NOTION_TASKS_DATABASE_ID`

The brief proposes 1–3 tasks/day here; still-open and recently-completed tasks feed back in.

| Property    | Type   | Options / notes                                   |
|-------------|--------|---------------------------------------------------|
| Tâche       | Title  |                                                   |
| Statut      | Select | `À faire`, `Fait`, `Abandonnée`                   |
| Domaine     | Select | must match `MEMO_AREAS`                           |
| Pourquoi    | Text   | why this task serves an objective                 |
| Retour      | Text   | result or blocker you write back; read by the brief |
| Source      | Select | `Brief`, `Manuel`                                 |
| Proposée le | Date   | tasks older than ~7 days with `À faire` are auto-abandoned |
| Faite le    | Date   | set when you mark a task `Fait`                   |

### Pages

| Page             | `.env` variable             | Role                                                                 |
|------------------|-----------------------------|----------------------------------------------------------------------|
| Daily Brief      | `NOTION_DAILY_BRIEF_PAGE_ID`| Brief output. Keep a permanent first block as a header — new briefs are inserted right after it (most recent on top). |
| Notes            | `NOTION_NOTES_PAGE_ID`      | Journal. Recognised `heading_2`/`heading_1` sections: contains `Aujourd` (today), `Journal`, `Todo`/`✅`. A `Archive`/`🗄` heading ends parsing. |
| Contexte Système | `NOTION_CONTEXT_PAGE_ID`    | Free text read each morning as the brief's system context (who you are, projects, priorities, copilot rules). No personal data lives in the code. |

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
