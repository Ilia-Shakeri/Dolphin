# Person Profile, Integrations Framework and Asterisk Connector — decision record

**Status: delivered.** Planned 2026-09-27 against `main` at `0d0c878` (v2.18.9);
every recommendation below (D1–D21) was approved by the product owner as
written, and shipped in six phases:

| Phase | Scope | Version | Contract |
|---|---|---|---|
| 1 | One profile page for customers and users, adapters, header, tabs | 2.19.0 | `docs/backend/PERSON_PROFILES.md` |
| 2 | Stat cards, explainable scores, completion bar, tasks, notes | 2.20.0 | `docs/backend/PERSON_PROFILES.md` |
| 3 | Integrations framework: providers, encrypted secrets, outbox, webhooks, API tokens | 2.21.0 | `docs/backend/INTEGRATIONS.md` |
| 4 | Asterisk / FreePBX connector: AMI listener, calls, CDR sync, recordings | 2.22.0 | `docs/backend/TELEPHONY.md` |
| 5 | Call popup, click-to-call, timeline / task / score hooks | 2.23.0 | `docs/backend/TELEPHONY.md`, `docs/ops/ASTERISK_GO_LIVE.md` |
| 6 | Full verification, PostgreSQL upgrade rehearsal from 2.18.0, push | — | `DOLPHIN_PROJECT_HANDOFF.md` |

This file keeps only the decisions, because code and docs cite them by number
(«decision D12» and so on). The design as built lives in the three contracts
above; the original analysis (inventory of the old pages, data sources,
infrastructure findings, risks) is in Git history:
`git show 5fa88ac:docs/PERSON_PROFILE_AND_INTEGRATIONS_PLAN.md`.

## Decisions

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | How tables refer to "a person" | (a) `person_type` + `person_id` pair validated by adapters; (b) explicit nullable FKs per type (the attachments pattern); (c) `ContentType` generic FK | **(a)** — a new person type needs only an adapter, no migrations on every person-linked table. Deletion is guarded in the adapter (refuse while calls/tasks exist, like `PROTECT`). |
| D2 | «درآمد» for users | (a) confirmed sales attributed to the user in the period (`Sale.sold_by`, the performance report's «مبلغ فروش»); (b) paid invoice amounts attributed to the user; (c) a commission rate × sales | **(a)** now, labelled with its definition in the tooltip. (c) invents compensation rules (CLAUDE.md §31) and needs a real commission policy first. |
| D3 | «بدهکاری» for customers | (a) ledger balance when `customer_ledger` is on, else issued-invoice outstanding; overdue = past-due invoices + overdue installments; (b) invoices only | **(a)**. Trend vs previous period only where the ledger's `balance_after` can answer it; otherwise «—» with a reason. |
| D4 | «مجموع خرید» | (a) issued, non-cancelled invoices; (b) confirmed sales; (c) both | **(a)** when `invoices` is on, **(b)** otherwise — never summed together (a sale that was invoiced would count twice). |
| D5 | «نرخ تبدیل» | (a) the dashboard gauge's definition — completed ÷ (completed + cancelled), leads decided in the period, assigned to the user; (b) your wording — completed ÷ assigned in the period | **(a)**, so the dashboard and the profile never show two different "conversion rates"; (b) reads low early in each month because undecided leads count against it. |
| D6 | Tasks | (a) new minimal `tasks` module (title, notes, due, assignee, person ref, status, completed_at, source) feeding the reminders bell; (b) no tasks — drop add-task, missed-call tasks and the on-time factor | **(a)**, behind the `tasks` flag. |
| D7 | Timeline | (a) hybrid: keep the nine pull sources + a push `TimelineEntry` store for new events; (b) backfill everything into one table | **(a)** — no history migration, integrations still push through one service. |
| D8 | Presence | (a) `User.last_seen_at`, written by middleware at most once per 2 minutes per user; online = seen in the last 5 minutes; (b) last login only | **(a)**. |
| D9 | Secret encryption | (a) add `cryptography` (hash-pinned, reviewed) and encrypt with `DOLPHIN_SECRETS_KEY`; (b) secrets only in `secrets/.env`, not editable in the UI | **(a)** — the only way to meet "write-only, encrypted, editable by an admin". Existing SMS/post plaintext secrets can move into it in a later release. |
| D10 | AMI client | (a) in-house asyncio client (~300 lines, no dependency); (b) `panoramisk` | **(a)** — AMI is a simple line protocol; full control over reconnect, heartbeat and the fake-server tests; no new dependency. |
| D11 | CDR access | (a) `PyMySQL` (pure Python, hash-pinned) against FreePBX's MariaDB `asteriskcdrdb.cdr`; (b) PBX team writes CDR to PostgreSQL (`cdr_pgsql`/ODBC); (c) AMI `Cdr` events only | **(a)**, with (c) as a supplementary live source. (c) alone cannot fill gaps while disconnected. |
| D12 | Popup transport | (a) short polling, 2 s, visible tabs only, indexed per-user query; (b) SSE (holds one Gunicorn thread per open tab — 12 threads total); (c) Channels + Redis (new services) | **(a)** — ≤ 2 s latency while the phone is still ringing, no new infrastructure; upgrade path kept behind one JS function. |
| D13 | Recordings | (a) read-only mount of the PBX recordings directory (NFS/SSHFS) on the Dolphin host; (b) PBX serves them over HTTPS to the CRM IP only | **(a)** if the PBX team can export a mount; **(b)** supported as the alternative. Both are configurable. |
| D14 | Processes | (a) one new Compose service `integrations-worker` running the AMI listener(s) plus periodic jobs (CDR sync, outbox, webhooks, health); nightly scores via crontab; (b) separate services per job | **(a)** — one thing to run and monitor; `run_telephony_listener` also exists standalone for debugging. |
| D15 | Existing «اتصال سامانه‌ها» page, SMS and post | (a) the new page supersedes it; SMS/post become built-in providers over their existing settings; (b) keep two pages | **(a)**. |
| D16 | The uncommitted `integration/` (accounting) app | (a) leave it untouched; new app is `integrations`; the accounting hand-off can become a provider once that work is decided; (b) merge now | **(a)** — it is protected, unreviewed work. |
| D17 | Public API tokens | (a) a token bound to a designated user (normal role + capability overrides) and narrowed by scopes; (b) standalone service tokens with their own permission model | **(a)** — reuses every permission and object-scope rule as-is. |
| D18 | Defaults | New flags off by default in the manifest builder; on for development; TIARA gets `telephony`/`integrations` only after its manifest is re-signed | As stated — please confirm which flags TIARA should get. |
| D19 | Git | (a) repo convention: commit to `main`, push `main` in Phase 6; (b) a feature branch | **(a)** — the repository has a clear convention (your instruction: follow it when one exists). |
| D20 | Telephony permission defaults | Agent: `calls.own`, `calls.originate`; Sales Manager / Company IT: `calls.company`, `calls.originate`, `calls.recordings`; Platform Admin: all | As stated, all adjustable per user in the matrix. |
| D21 | Score defaults | Customer: recency 25, frequency 20, monetary 20, punctuality 25, engagement 10. User: task on-time 20, conversion 30, follow-up speed 20, activity 20, missed-call follow-up 10 | As stated, editable by Platform Admin. |
