# 🐬 Dolphin

**سامانه مدیریت ارتباط با مشتری** — a Persian-first, RTL CRM/ERP panel for
sales, billing, inventory, and after-sales, built as one shared codebase
deployed separately per customer.

Dolphin runs a customer's whole commercial pipeline in one place: campaigns,
leads and call-center activity → quotations, supply requests, and invoices →
payments, cheques, and installments → inventory and stock movements → postal
tracking → after-sales tickets — with a full audit trail, a per-user permission
system layered on top of role-based defaults, and a panel that updates live.

---

## Why it's built this way

- **One codebase, many deployments.** Every customer gets their own database,
  secrets, and runtime identity — never `if client_name == ...` scattered
  through the code. Feature availability, role permissions, and object/data
  scope are three independent controls, and disabling a feature never deletes
  history.
- **Backend-enforced, not UI-enforced.** Every protected endpoint checks the
  effective permission itself. A hidden button is a UI convenience, never the
  authorization boundary.
- **Evidence over assumption.** Business rules live in code and in
  [`BACKEND_SPEC.md`](BACKEND_SPEC.md), not in memory. Tests are run, not
  imagined; findings are backed by an actual traceback, not a guess.

## What's inside

| Area | Django app | Covers |
|---|---|---|
| Accounts & access | `accounts` | Users, roles, per-user capability overrides, sessions |
| Sales | `sales` | Customers, leads (shared out evenly among a campaign's responsible people), interactions, campaigns and sub-campaigns with analytics, products, postal tracking and the Iran Post connection |
| Billing | `billing` | Quotations, orders, invoices, payments, cheques, installments, customer ledger |
| Inventory | `inventory` | Warehouses, stock levels, stock movements |
| After-sales | `aftersales` | Service requests, assignment, status history |
| Communications | `communications` | Outbound SMS (single, bulk, scheduled) through a configurable gateway; inbound SMS |
| Profiles | `profiles`, `timeline`, `tasks`, `scoring` | One profile page for customers and colleagues: stat cards, explainable scores, timeline, tasks, notes |
| Integrations | `integrations` | Connections with encrypted secrets, signed inbound/outbound webhooks, API tokens, event outbox |
| Telephony | `telephony` | Asterisk/FreePBX: live call capture, CDR sync, recordings, call popup, click-to-call |
| Collaboration | `chat`, `attachments` | Internal chat, file attachments |
| Reports | `reports` | User and company performance, marketer ranking, receivables, gross profit, stock valuation, customer ledger, step-by-step postal and inbound-SMS reports, list charts, XLSX exports |
| Accounting link | `accounting`, `integration` | Phase 1 of the separate Dolphin Accounting product: a neutral general ledger (off by default) and the signed CRM↔Accounting pairing |
| Audit | `auditlog` | Append-only activity log, Persian-labeled |
| Shell | `common` | The served UI, permissions plumbing, deployment profile, panel backups, live updates (SSE), navigation registry, static assets |

The panel itself lives in `common/templates/common/**` +
`common/static/common/dolphin.css` + the panel script, routed through
`common/ui_urls.py`/`common/ui_views.py`. The reference template folder at the repository root is visual reference
only — never served, never a source of business rules, and nothing in the
panel depends on it.

## Stack

- **Backend:** Django 5.2 + Django REST Framework, Python 3.13 (pinned base image; no new runtime dependency is added casually)
- **Database:** PostgreSQL (SQLite for the default local/test run)
- **Frontend:** Server-rendered Django templates, RTL, Persian (`fa`) —
  Dolphin UI kit (`common/static/common/ui/`) + a first-party layer of ES modules
  (`common/static/common/js/`, loaded per page through an import map) and one
  stylesheet, no build step
- **Auth:** Session-based, role defaults + per-user capability overrides
- **Deployment:** Docker Compose, nginx edge, signed feature-manifest per
  customer

## Getting started locally

```bash
git clone https://github.com/Ilia-Shakeri/Dolphin.git
cd Dolphin
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

By default this runs against SQLite with no extra setup. For a real
PostgreSQL stack (the shape production actually runs), see
[`docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md`](docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md)
— the canonical, no-assumptions guide for installing, updating, backing up,
and recovering a real deployment. Every pre-existing `docs/ops/*.md` file
was merged into it 2026-09-01 (one doc, not fourteen), each former file
preserved intact as its own section; two narrower, customer/provider-specific
runbooks were added afterward and stay separate on purpose — see the
documentation map below.

## Testing

```bash
python manage.py test --settings=config.test_settings
```

Runs the suite (about 3,400 non-browser tests as of 2.40.34) against an
isolated SQLite database — no external services required. Run it serially
(`--parallel` does not work with the temporary SQLite database on Windows). The
`*_browser` Selenium tests need a real browser stack and are not part of the
routine run. A database-role or grant change is not proven by SQLite: run the
suite against PostgreSQL 16 too (`config._pg_tmp_settings`, or the isolated
PostgreSQL proof suite in the "Isolated PostgreSQL testing" section of
[`BACKEND_SPEC.md`](BACKEND_SPEC.md)).

> **Use `config.test_settings`, not `config.devcheck_settings`.** The latter
> exists only to serve the panel in a browser for visual checks: it points at
> a real on-disk SQLite file rather than the per-process temporary database
> the suite expects. Several tests assert on the database identity on purpose
> — the synthetic-UAT seed command refuses to run against anything that is not
> a recognised isolated target — so running the suite under `devcheck_settings`
> produces confusing failures that say nothing about the code.

## Documentation map

| Document | What it's for |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Repository rules: authority order, architecture, branding, working style |
| [`BACKEND_SPEC.md`](BACKEND_SPEC.md) | The normative business/backend contract, plus the merged entity/relationship/API/semantics reference (see its Appendix) |
| [`DOLPHIN_PROJECT_HANDOFF.md`](DOLPHIN_PROJECT_HANDOFF.md) | The live status and evidence register |
| [`DOLPHIN_FEATURE_MAP_AND_ROADMAP.md`](DOLPHIN_FEATURE_MAP_AND_ROADMAP.md) | What exists today, what shipped, and the one list of remaining work |
| [`CHANGELOG.md`](CHANGELOG.md) | Every release, what changed and why |
| [`docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md`](docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md) | Deployment, backup/restore, rollback, security, incident response — the primary ops document |
| [`DOLPHIN_ACCOUNTING_PLAN.md`](DOLPHIN_ACCOUNTING_PLAN.md) | Analysis and phasing of the accounting product, with the open questions that need the owner's or an accountant's decision |
| [`docs/PERSON_PROFILE_AND_INTEGRATIONS_PLAN.md`](docs/PERSON_PROFILE_AND_INTEGRATIONS_PLAN.md) | Decision record D1–D21 behind profiles, integrations and telephony (delivered) |
| [`docs/DOLPHIN_CAPABILITIES_FOR_INVOICE_FA.txt`](docs/DOLPHIN_CAPABILITIES_FOR_INVOICE_FA.txt) | The numbered capability list used in customer paperwork (Persian); its status marks are stale, the roadmap is the truth |
| [`docs/backend/PERSON_PROFILES.md`](docs/backend/PERSON_PROFILES.md), [`INTEGRATIONS.md`](docs/backend/INTEGRATIONS.md), [`TELEPHONY.md`](docs/backend/TELEPHONY.md), [`SHIPPING.md`](docs/backend/SHIPPING.md) | Contracts of the profile, integrations, telephony and Iran Post shipping modules |
| [`docs/ops/ASTERISK_GO_LIVE.md`](docs/ops/ASTERISK_GO_LIVE.md), [`PBX_CONNECTION_GUIDES.md`](docs/ops/PBX_CONNECTION_GUIDES.md) | Connecting a customer's Asterisk/FreePBX step by step; per-brand guides for other PBXs |
| [`docs/ops/CUSTOMER_FEATURE_UPDATE_GUIDE.md`](docs/ops/CUSTOMER_FEATURE_UPDATE_GUIDE.md) | Turning on a new feature module for an existing customer, without repeating the runbook |
| [`docs/ops/PROVIDER_CONNECTION_GUIDE.md`](docs/ops/PROVIDER_CONNECTION_GUIDE.md) | Connecting any real SMS/post provider to the generic settings pages — field by field, provider-agnostic |
| [`docs/ops/TIARA_SMS_SETUP.md`](docs/ops/TIARA_SMS_SETUP.md) | TIARA-specific SMS provider field values — one deployment, one time, not a general guide |

`docs/brand-source/logos/` holds the source logo files (not documentation); the
served copies are in `common/static/common/brand/`.

The older `docs/backend/` and `docs/frontend/` notes were merged into
`BACKEND_SPEC.md`'s Appendix; `docs/backend/` holds only the module contracts
above. One-shot task prompts and superseded draft plans are not kept in the
tree — they are in Git history.

## Versioning

`MAJOR.MINOR.PATCH`, tracked in [`VERSION`](VERSION) and read by
`config/settings.py` at startup. See `CHANGELOG.md`'s numbering rule for what
moves which digit. Each release is one commit and one `vX.Y.Z` tag on the
working release branch (`release/2.40` today), fast-forwarded to `main`.

---

<sub>Internal engineering identifiers from the product's earlier names
(`forooshbin`, `Kariz`) were fully renamed to Dolphin as of 2026-09-01. A
fixed set of `KARIZ_*` deployment environment variable names was deliberately
kept until 2026-09-05, when the product owner closed that last exception
too — every `.env`-facing name is now `DOLPHIN_*`. An already-deployed
`.env` still using the old names needs a one-time manual update before its
next deploy; see the migration note in `docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md`.</sub>
