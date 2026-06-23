# Daily Brief — example

This is an **illustrative** example of what the Daily Brief writes to your Notion page each
morning. All content is fictional (a generic indie-maker persona); your real brief is generated
from your own Objectives, Tasks, captures and notes. It follows the exact structure produced by
`bridge/memo-bridge.py` — the `Today's tasks` section is parsed back into the Tasks database.

---

## 🗓️ Daily Brief — 22/06/2026

### 📌 Follow-up
- "Ship onboarding emails" (done yesterday) — the first signups received it; the logical next step
  is to measure the open rate before writing email #4.
- "Refactor billing webhook" is still open since Monday — still the priority: it blocks the paid launch.

### 🔗 Connections
- Your note "users churn after day 2" connects to the objective "reach 50 paying users": the lever
  is **activation**, not signups. Instrument the onboarding flow before pushing more traffic.

### ⚡ Contradictions / blind spots
- You name growth as your priority, but 4 of your 5 open tasks are infrastructure. The compass says
  growth — the work says maintenance.

### ✅ Today's tasks
- **[Projects]** Add an activation event to the onboarding flow — measures the day-2 drop you flagged
- **[Work]** Send the billing-webhook fix for review — unblocks the paid launch
- **[Health]** 30-min zone-2 run — recovery day in your plan

### 🎓 To learn
- Postgres partial indexes — your webhook query scans the whole events table; a partial index is the
  cheap win.

### ❓ Question to explore
- What single metric would tell you the product is "working" — and are you instrumenting it today?
