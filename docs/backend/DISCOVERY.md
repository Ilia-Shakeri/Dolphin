# Backend discovery

## Repository state

The active directory contains a static Metronic-style frontend and no Django project. The root `AGENTS.md` is present. The three higher-context backend files named by the instructions are absent. There is no `.git` directory in the active root, so Git diff checks cannot run.

No backend, settings, migrations, tests, requirements, deployment files, or sanitized environment example existed at discovery time. This is disposable initial backend state, not an existing migration history.

Production settings are PostgreSQL-only. `config/test_settings.py` uses ephemeral in-memory SQLite solely for host-side logic tests when PostgreSQL is unavailable; it is not deployment or migration proof.

`config/postgres_test_settings.py` and `scripts/test-postgres.ps1` provide a fail-closed native PostgreSQL test path. See `docs/backend/POSTGRES_TESTING.md`. The current host still lacks the required native PostgreSQL tools, so this path is not yet runtime proof.

## Frontend evidence

Bounded checks found an email/password sign-in form and customer/user profile fields. The scripts mostly simulate success and contain commented form submissions. They are not network contracts or business truth. No business status, permission, assignment, or report rule was accepted from them.

## Chosen structure

- `accounts`: custom user, fixed CRM roles, session endpoints, profile and controlled user administration.
- `sales`: customer, phone, lead, assignment history, interaction, product, and sale.
- `auditlog`: append-only sensitive action records.
- `common`: timestamps, phone normalization, scoped-query helpers, and health check.
- `reports`: reserved for approved report formulas; no ambiguous KPI is published.
- `config`: settings and versioned routing.

## Migration decision

Initial migrations and additive role, assignment, money, and Sale-state constraint migrations are safe because no backend or prior migration history exists. They must be applied only to a new PostgreSQL database. No production migration reset is authorized.

## Blockers

See `ASSUMPTIONS.md`. Reports/XLSX, lead transitions, fixed interaction enums, Company IT company scope, and optional support wait for `BACKEND_SPEC.md`.

Production settings require an explicit long secret. TLS redirect and HSTS are opt-in because this repository has no certificate or approved edge termination details. Enable them only with the real HTTPS path in place. The bundled layout has exactly one trusted application proxy. Nginx discards caller forwarding chains. Audit IP capture trusts `X-Real-IP` only when the direct peer belongs to an exact CIDR listed in `AUDIT_TRUSTED_PROXY_CIDRS`; the default trusts no proxy CIDR.

Compose uses a one-shot migration/static collection service before Gunicorn starts. Nginx serves collected static files, applies a login rate cap, and uses its own connection scheme for forwarded-protocol trust.
