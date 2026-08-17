# Backend discovery

> This document is a technical discovery snapshot, not live project status. Current progress, blockers, evidence, and exact next action exist only in `KARIZ_PROJECT_HANDOFF.md`.

## Repository state at the discovery snapshot

The active root is `Kariz-CRM`. It contains a Django modular-monolith backend, PostgreSQL production settings, migrations, tests, Docker Compose, Nginx configuration, a large static template tree, and local Git metadata with initial commit `ef1c7f4`.

`BACKEND_SPEC.md` is now present and is the provisional authoritative business source. The older named backend prompt and frontend context files remain absent under canonical or obvious suffixed root names. Work must use the specification, durable goal, approved backend documents, current migrations, and tests without treating demo pages as business truth.

The prior discovery statement that no backend, Git, or specification existed is obsolete. It described the earlier scaffold start, not the current tree.

## Backend structure

- `accounts`: custom user, fixed roles, CRM/server identity separation, session endpoints, profile, controlled user administration, and last-active-Platform-Admin guard.
- `sales`: Customer, CustomerPhone, Lead, assignment history, Interaction, Product, and Sale.
- `auditlog`: sensitive activity records, actor/account-target role-at-action snapshots, safe change filtering, and scoped read-only API.
- `common`: timestamps, phone normalization, request context, permissions, strict serializer input, bounded JSON parsing/body size, stable errors, and health routes.
- `reports`: implemented exact user-performance JSON/XLSX projection with shared scoped service, safe filters, and no persisted model.
- `config`: base, test, production, and isolated PostgreSQL-test settings plus versioned routing.

## Runtime topology

Compose defines six normal services: PostgreSQL, a pre-migration database-role bootstrap, a one-shot migration/static job, a post-migration exact-grant finalizer, Gunicorn, and Nginx. A profile-only seventh service runs guarded backups. A separate one-service restore definition has no network, target database, or database secret; it reads the backup volume and builds a disposable cluster in bounded tmpfs. Exact external PostgreSQL data and backup volumes are required. The init login is confined to database/bootstrap/finalize work; the migration login owns the database/schema and runs migrations; the application login receives only the exact table/sequence rights named after migration and no schema-owner role; the separate backup login is read only. Only `web` joins both the internal database network and the frontend network, so Nginx cannot resolve PostgreSQL.

Production Compose has no local build path and requires digest-qualified application, PostgreSQL, and Nginx image references. The Dockerfile requires a digest-qualified Python base input. Real reviewed digest values and built-artifact proof remain external. A reversible Nginx write-stop override rejects POST/PUT/PATCH/DELETE while reads and health remain available.

The application service is not host-published. Nginx is the sole bundled public hop, publishes 80/443, leaves only its exact local HTTP liveness path unredirected, redirects other HTTP traffic to the validated public host, and terminates TLS 1.2/1.3 using exact external certificate/key file mounts. HTTPS proxy paths overwrite forwarding headers, set `X-Forwarded-Proto` to `https`, own the edge request ID, and rate-limit both CRM and admin login paths. Production validation requires HTTPS redirect plus at least one year of HSTS, while live certificate, TLS, and HSTS response proof remains external. Production also removes schema and interactive-doc URL patterns; test settings keep controlled schema generation.

The excluded static archive remains outside `TEMPLATES.DIRS` and the backend image. The active repository UI is the first-party Persian/RTL `common` root shell plus branded Django admin. The archive remains untouched and unserved by this stack; unknown external use and browser proof remain separate.

## Migration and test state

Current migration heads are `accounts.0002_user_role_constraint`, `auditlog.0002_activitylog_role_snapshots`, and `sales.0010_interaction_contract`. Sales `0006` makes active normalized phone identity global, `0007` requires positive Product price, `0008` aborts on invalid stored phone shapes before adding the ASCII `+98[1-9][0-9]{9}` database check, `0009` preflights then caps six free-text columns without copying values into errors, and `0010` requires exact inbound/outbound Interaction direction plus a nonblank outcome. Normal request bodies stop at 256 KiB — sized from the largest document the API accepts — JSON stops at 32 container levels, and oversized input returns stable HTTP 413 before a write.

The isolated PostgreSQL harness is fail-closed and avoids Compose, port 5432, caller production variables, and persistent volumes. On a host with approved native tools plus a compatible Bash path, it creates one random loopback-only temporary cluster, runs the full PostgreSQL suite, migrates a valid business graph from `sales.0004` through `sales.0010`, applies the real role bootstrap/finalizer, probes exact application and backup grants/denials, completes a backup-role dump, and forces a mid-transaction owner failure to prove rollback. The cluster and all proof data are removed only through the token-bound temporary path guard.

Fast tests use in-memory SQLite only. Native PostgreSQL, Docker, and Nginx executables were absent in the last host probe. The PostgreSQL-only concurrency, migration, ACL, denial, dump, and rollback cases therefore remain external runtime proof gaps, not substitutes for repository checks.

## Safety state

Git exists, user identity is configured, and reviewed baseline commit `50a978a` exists. The worktree contains ongoing reviewed implementation batches. The exact current-worktree source manifest has 117 paths, but no user-approved immutable release reference binds it yet. Ignore manifests exclude secret, certificate/key, database, backup, log, generated export, and inactive archive artifacts from the backend image or Git as applicable. Final immutable-reference and staged/deployment scans remain release gates.

## Gaps recorded at the discovery snapshot

- Keep undefined Lead/report/presentation/after-sales behavior excluded until approved.
- Finish the active operations follow-up, refresh exact release evidence, and run a fresh final repository audit.
- Record one user-approved immutable release reference and regenerate proof against it.
- Prove PostgreSQL role/grant/migration behavior, container boot, proxy/static/direct TLS, browser paths, backup/restore, alerts, and recovery on approved external runtimes.

See `KARIZ_PROJECT_HANDOFF.md` for live status, completed work, assumptions, blockers, and exact continuation commands.
