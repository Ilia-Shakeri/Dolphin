# Release notes - source candidate 2026-08-10

## Release identity

This source candidate is an uncommitted reviewed delta based on Git commit `50a978abc206e43032ce96b36dc0433366198e60` (`chore: establish durable production roadmap`). `docs/ops/SOURCE_MANIFEST.md` exactly records its 134-path working-tree set and proof boundary, but the worktree is not an immutable deploy or rollback artifact. Explicit user authorization is still required to create or name that reference. State B may use only `production candidate; external verification pending` after the final repository audit confirms no P0/P1; the immutable artifact remains an explicit human-input blocker.

## Main changes

### Identity, authorization, and audit

- Added fail-closed CRM identity gates that exclude Django staff, superusers, group-linked users, and direct-permission users from CRM actors, targets, directories, assignments, and reports.
- Added a locked last-active-Platform-Admin guard and a first-ever Platform Admin bootstrap command with hidden password prompts and safe audit output.
- Added stored audit actor/object role snapshots. Company IT cannot view Platform Admin or unknown legacy role rows; Platform Admin retains full read scope.
- Added read-only activity-log list/retrieve routes for Company IT and Platform Admin.
- Added strict password validation, server-field rejection, unknown/repeated query rejection, inactive-user denial, and direct-ID/non-enumeration tests.
- Allowed elevated operators to inspect and reactivate a clean inactive CRM user while keeping unrelated inactive-user mutations denied. Deactivation with active assigned Leads preserves exact ownership/history and performs no implicit move until BIZ-013 is approved.
- Added safe API CSRF and server-fault JSON responses with one request ID. Logs omit exception text, query strings, bodies, headers, and secrets.
- Added typed OpenAPI error envelopes and exact request/no-body/400/403/404/409 contracts for custom actions.
- Added stable user-keyed throttling and `429 throttled` contracts for user changes, Customer/Product deactivation, Lead reassignment, Sale create/cancel, audit reads, report JSON, and XLSX export.

### CRM data and transitions

- Made active normalized phone identity globally unique and restricted stored values to the exact ASCII Iran shape.
- Made Product price strictly positive.
- Tightened Lead assignment, Sale state, snapshot-pair, quantity, money, and snapshot-total database guards.
- Kept Interaction, assignment history, and audit paths append-oriented; the production application database role has no update/delete right on those tables.
- Fixed Interaction direction to `inbound` or `outbound`, trims required outcome text to 80 characters, and rejects blank outcomes in models, APIs, services, and migration `sales.0010` without inventing outcome codes.
- Added atomic locked services, no-op/conflict handling, Product/Sale snapshots, and role/object attack tests.
- Capped request bodies at 64 KiB, JSON nesting at 32 container levels, Customer address at 2,000 characters, and the five notes/description fields at 4,000. Oversized input returns stable `payload_too_large` HTTP 413; malformed and deep JSON returns a safe parse error. All fail before a write.

### Reports and active application

- Added scoped user-performance JSON and XLSX routes with exact half-open date filters, optional authorized user/Product filters, deterministic two-decimal values, zero-denominator handling, no-store responses, and workbook formula defense.
- Added flat query-growth proof from one to five rows for users, activity logs, customers, phones, leads, interactions, products, and sales list routes.
- Added a first-party Persian/RTL root shell and Persian Kariz admin branding with local static assets and no active vendor/demo link.
- Disabled schema and interactive API documentation routes in production; authenticated routes remain available in test/development settings.

### Production source and operations

- Added strict production environment parsing for one exact public host/origin, secure cookies, direct TLS, checked HSTS, proxy trust with IPv4/IPv6 `/0` rejection, timeouts, and split database roles.
- Added a bounded file-based throttle cache under the platform portable temporary root. It is shared by workers in the approved single web container; horizontal web scaling still needs an approved shared store and new runtime proof.
- Added six normal Compose services: database, role bootstrap, migration/static job, exact post-migration grant finalizer, read-only Gunicorn web, and direct-TLS Nginx. A profile-only seventh service runs guarded backups over the internal database network. The four database logins are init, migration, application, and read-only backup.
- Required one stable Compose project name across release directories, suppressed PostgreSQL statement/parameter/connection-duration logs, bounded default Django logs, and routed query-free Nginx access/error streams through bounded container logs. Unversioned static paths revalidate instead of receiving stale multi-day freshness.
- Added exact runtime table/sequence/routine database privileges, default deny for future application rights, and no public/application routine execution.
- Added a separate read-only backup login, exact external backup volume, checked dump/checksum/retention job with an atomic overlap lock, and a no-network disposable restore job. Host and container verifiers share one true-result contract for nine core tables, three migration heads, twelve constraints, and two partial unique indexes.
- Required exact external PostgreSQL data and backup volume names and split backend/frontend networks.
- Added a reversible edge write-stop that blocks POST/PUT/PATCH/DELETE while reads and health remain live.
- Removed local builds from production Compose. Compose interpolation itself requires nonempty image inputs; the mandatory validator and release workflow reject missing, mutable, uppercase, or malformed refs and require version plus lowercase SHA-256 digest for all four images. The Docker build also verifies its base digest, Linux/amd64 platform, and Python 3.13 interpreter.
- Added guarded native PostgreSQL test, backup, restore-verification, bootstrap, UAT seed, dependency, deployment, TLS, rollback, incident, and release procedures, including exact no-`down` full-stack stop/restart and application/edge/config rollback paths.
- Expanded the guarded native PostgreSQL harness to run the full target-engine suite, a 0004-to-0010 upgrade, real role bootstrap/finalizer, exact ACL/denials, backup-role dump, and injected-failure rollback in one token-bound loopback temporary cluster.
- Added a bounded GET-only health load harness with strict target confirmation, no proxy/redirect/credential/body support, local loopback tests, and an exact approval/evidence runbook.
- Added an exact external security-evidence runbook for digest-pinned source/dependency/SBOM/image/TLS scanners, reduced secret findings, restricted sealed reports, reviewer disposition, and an out-of-band integrity anchor.
- Added an exact SHA-256 dependency lock and require-hash binary-only image install. Reviewed real image/scanner digests, SBOM, and current external scans remain blocked proof.

## Migrations and data impact

- `sales.0006_global_active_phone_identity` aborts if active normalized phone values conflict. It does not merge or delete data.
- `sales.0007_product_price_positive` aborts if an existing Product price is not positive. It does not rewrite prices.
- `sales.0008_customer_phone_normalized_shape` aborts with bounded row IDs when stored normalized phones are not canonical ASCII `+98[1-9][0-9]{9}`. It does not fold or rewrite stored values because that could create identity collisions.
- `auditlog.0002_activitylog_role_snapshots` adds nullable actor/object role snapshots. Legacy values remain blank rather than being guessed from a user's current role.
- `sales.0009_bounded_free_text` reports bounded offending row IDs before changing six former free-text columns to length-limited types. It does not copy or rewrite stored text.
- `sales.0010_interaction_contract` reports bounded offending row IDs before fixing direction choices and outcome length, then adds direction-membership and trimmed-nonblank outcome constraints. It does not guess or rewrite an outcome.

All target-engine zero/upgrade application, lock behavior, constraint behavior, and existing-data preflight results still require isolated PostgreSQL proof before deployment.

## Endpoint summary

- Authentication: `/api/v1/auth/login/`, `/logout/`, `/me/`.
- User administration: `/api/v1/users/` plus dedicated role change.
- CRM: customers/deactivate, customer phones, leads/reassign, interactions read/create, products/deactivate, sales/cancel.
- Audit: read-only `/api/v1/activity-logs/` list/retrieve.
- Reports: `/api/v1/reports/user-performance/` and `/api/v1/exports/user-performance.xlsx`.
- Health: application live, database ready, compatibility health, and edge live paths.
- Active UI: `/` and `/admin/`.
- Schema/docs: authenticated outside production; absent from the production URL map.

Sale correction, Team administration, optional after-sales, undefined KPI fields, unapproved Lead statuses, and unapproved Interaction outcome groupings are not present. Interaction direction is already fixed to inbound/outbound.

## Local verification evidence

- Full fast suite: 226 tests completed successfully; six PostgreSQL-only cases skipped on SQLite as designed.
- Test-settings system check: passed.
- Migration drift: no changes detected.
- Non-production OpenAPI validation with warnings fatal: passed under UTF-8 output.
- Static collection dry run: passed.
- Python package consistency: passed.
- Mandatory release-image reference validator: passed with non-secret test refs.
- Strict safe-value production deploy check exited zero; only the deliberate HSTS subdomain/preload warnings remained.
- PostgreSQL bootstrap, backup, restore, native-harness Bash/PowerShell, load, and scan-runbook syntax/source gates: passed.
- Exact source manifest: 134 paths, comprising 47 modified and 87 added paths; no delete or rename.
- Changed/untracked path policy and high-confidence secret-pattern scans: 0 blocked paths and 0 matches.
- Active-file ledger: 179 unique live first-party rows with exact Phase 1 links and no missing or stale path.
- Final source re-review: pending the independent final backend and operations audit reports.

## Known limits and release state

Current claim remains `work in progress` until the independent final repository audits confirm no P0/P1. If they pass, State B permits only `production candidate; external verification pending`; the unapproved immutable reference remains explicit SRC-002/OPS-001 human input and still blocks deployment, rollback identity, and State A.

Business decisions and external proof gaps are listed in `BLOCKERS.md`. In particular, live PostgreSQL ACL/migration/backup proof, Docker/Nginx/write-stop boot, certificate/TLS scan, browser smoke, capacity/load proof, real application/scanner digests, SBOM/scans, backup policy, and an exact release reference remain open. The hashed dependency lock, Docker build gates, and mandatory image validator exist; Compose interpolation alone proves only nonempty refs. No real digest value is guessed here.

## Rollback boundary

This uncommitted source delta is not a deployable rollback point. Do not use a destructive Git reset or broad file cleanup. Create and review an exact release artifact first. Deployment rollback must then follow `docs/ops/ROLLBACK.md` with a prior artifact, compatibility review, approved recovery point, and no in-place restore or volume deletion.
