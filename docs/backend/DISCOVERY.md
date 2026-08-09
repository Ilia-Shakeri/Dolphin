# Backend discovery

## Current repository state

The active root is `Kariz-CRM`. It contains a Django modular-monolith backend, PostgreSQL production settings, migrations, tests, Docker Compose, Nginx configuration, a large static template tree, and local Git metadata with initial commit `ef1c7f4`.

`BACKEND_SPEC.md` is now present and is the provisional authoritative business source. The older named backend prompt and frontend context files remain absent under canonical or obvious suffixed root names. Work must use the specification, durable goal, approved backend documents, current migrations, and tests without treating demo pages as business truth.

The prior discovery statement that no backend, Git, or specification existed is obsolete. It described the earlier scaffold start, not the current tree.

## Backend structure

- `accounts`: custom user, fixed roles, session endpoints, profile, and controlled user administration.
- `sales`: Customer, CustomerPhone, Lead, assignment history, Interaction, Product, and Sale.
- `auditlog`: sensitive activity records and safe change filtering.
- `common`: timestamps, phone normalization, request context, permissions, strict serializer input, and health routes.
- `reports`: installed app; report implementation is now unblocked for exact metrics named by the specification.
- `config`: base, test, production, and isolated PostgreSQL-test settings plus versioned routing.

## Runtime topology

Compose defines PostgreSQL, a one-shot migration/static collection job, Gunicorn, and Nginx. The application service is not host-published. Nginx is the sole bundled public hop, overwrites forwarding headers, owns the edge request ID, and rate-limits login. Production settings require an environment secret and secure cookies.

The root static template tree is excluded from the backend container by `.dockerignore`; no active template integration is yet proven. Phase 6 and Phase 7 must identify or create the actual active Kariz UI before any deletion-heavy cleanup.

## Migration and test state

Current migrations include the custom user and Sales migrations through `sales.0005_sale_integrity_constraints`. The isolated PostgreSQL harness is fail-closed and avoids Compose, port 5432, caller production variables, and persistent volumes.

Fast tests use in-memory SQLite only. Native PostgreSQL, Docker, and Nginx executables were absent in the last host probe. Those are external runtime proof gaps, not substitutes for repository checks.

## Safety state

Git exists and user identity is configured. The source and durable goal files are untracked at this checkpoint. `.gitignore` is being expanded before the new baseline commit. High-confidence tracked-secret and forbidden-path scans found no private-key or known live-token pattern; broader policy checks continue before staging.

## Main active gaps

- Reconcile implementation authorization and phone identity rules against the now-present specification.
- Build exact predefined reports and matching XLSX export.
- Establish active Persian-only UI and Kariz branding boundaries.
- Add backup, restore, log rotation, release, and incident operations.
- Prove PostgreSQL, container, proxy, static, TLS, backup, and restore behavior when runtime inputs exist.

See `PROJECT_ROADMAP.md`, `PRODUCTION_READINESS_CHECKLIST.md`, `BLOCKERS.md`, and `WORKLOG.md` for live status.
