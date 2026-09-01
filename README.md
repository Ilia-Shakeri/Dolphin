# 🐬 Dolphin

**سامانه مدیریت ارتباط با مشتری** — a Persian-first, RTL CRM/ERP panel for
sales, billing, inventory, and after-sales, built as one shared codebase
deployed separately per customer.

Dolphin runs a customer's whole commercial pipeline in one place: leads and
call-center activity → quotations, orders, and invoices → payments, cheques,
and installments → inventory and stock movements → after-sales tickets — with
a full audit trail and a per-user permission system layered on top of
role-based defaults.

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
| Sales | `sales` | Customers, leads, interactions, campaigns, products |
| Billing | `billing` | Quotations, orders, invoices, payments, cheques, installments, customer ledger |
| Inventory | `inventory` | Warehouses, stock levels, stock movements |
| After-sales | `aftersales` | Service requests, assignment, status history |
| Communications | `communications` | Inbound SMS |
| Reports | `reports` | Company and user performance |
| Audit | `auditlog` | Append-only activity log, Persian-labeled |
| Shell | `common` | The served UI, permissions plumbing, static assets |

The panel itself lives in `common/templates/common/**` +
`common/static/common/dolphin.css` + `dolphin-app.js`, routed through
`common/ui_urls.py`/`common/ui_views.py`. Everything under `assets/`, `apps/`,
`dashboards/`, `pages/`, and friends is the purchased Metronic theme's own
demo content — visual reference only, never served, never a source of
business rules.

## Stack

- **Backend:** Django 5.2 + Django REST Framework, Python 3.13
- **Database:** PostgreSQL (SQLite for the default local/test run)
- **Frontend:** Server-rendered Django templates, RTL, Persian (`fa`) —
  Metronic theme + a small first-party JS/CSS layer, no build step
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
and recovering a real deployment.

## Testing

```bash
python manage.py test --settings=config.test_settings
```

Runs the full suite (1,000+ tests) against an isolated SQLite database — no
external services required. For the isolated-PostgreSQL proof suite that
exercises the real role/grant contract, see
[`docs/backend/POSTGRES_TESTING.md`](docs/backend/POSTGRES_TESTING.md).

## Documentation map

| Document | What it's for |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Repository rules: authority order, architecture, branding, working style |
| [`BACKEND_SPEC.md`](BACKEND_SPEC.md) | The normative business/backend contract |
| [`DOLPHIN_PROJECT_HANDOFF.md`](DOLPHIN_PROJECT_HANDOFF.md) | The live status and evidence register |
| [`DOLPHIN_CLIENT1_CODEX_ROADMAP.md`](DOLPHIN_CLIENT1_CODEX_ROADMAP.md) | The phased delivery plan |
| [`DOLPHIN_FEATURE_MAP_AND_ROADMAP.md`](DOLPHIN_FEATURE_MAP_AND_ROADMAP.md) | What exists today vs. what's next |
| [`CHANGELOG.md`](CHANGELOG.md) | Every release, what changed and why |
| [`docs/backend/`](docs/backend) | Entity/relationship/API contracts, business semantics |
| [`docs/ops/`](docs/ops) | Deployment, backup/restore, rollback, security, incident response |

## Versioning

`MAJOR.MINOR.PATCH`, tracked in [`VERSION`](VERSION) and read by
`config/settings.py` at startup. See `CHANGELOG.md`'s numbering rule for what
moves which digit.

---

<sub>Internal engineering identifiers from the product's earlier names
(`forooshbin`, `Kariz`) do not appear anywhere in this codebase as of
2026-09-01 — see `CLAUDE.md`'s Branding section for exactly what changed and
why.</sub>
