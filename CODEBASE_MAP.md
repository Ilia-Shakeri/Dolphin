# Codebase map

## Repository and boundaries

- Root: `Kariz-CRM`.
- Git safety base: initial commit `ef1c7f4`; durable source/roadmap baseline commit `50a978a`.
- Active backend: first-party Django apps plus `config`, deployment files, and backend docs.
- Static template archive: root HTML and large `account/`, `apps/`, `authentication/`, `assets/`, `src/`, layout/demo trees. It is not copied into the backend image, is absent from `TEMPLATES.DIRS`, and has no repository URL entry. It is unserved by the current stack but may have an unknown external consumer.
- Never review dependency/vendor/minified/media/font/binary/cache trees as application logic.

## Django apps

| App | Responsibility | Main entry points | Main data |
|---|---|---|---|
| `accounts` | Custom user, session auth/profile, user and role administration | auth URLs, user router/viewset | User |
| `sales` | Operational CRM records and transitions | sales router/viewsets, services/selectors | Customer, CustomerPhone, Lead, history, Interaction, Product, Sale |
| `auditlog` | Sensitive activity persistence, safe payload filtering, and scoped read-only access | transition service calls and activity-log router | ActivityLog |
| `common` | Base model, permissions, request context, strict input, phone normalization, health, and first-party Persian shell | middleware, health routes, `/`, admin branding | shared behavior and UI |
| `reports` | Exact predefined metrics and matching machine-readable XLSX | report/export routes, scoped service, workbook builder | read-only projections; no model |
| `config` | Settings, URL root, WSGI/ASGI, PostgreSQL test guard | application process | runtime configuration |

## Request, auth, and audit flow

```text
Browser -> Nginx direct TLS / HSTS / request ID / rate / fixed proxy headers
        -> RequestContextMiddleware
        -> Security / session / CSRF / authentication
        -> active-user permission
        -> role-scoped viewset/queryset
        -> strict serializer
        -> locked service transition
        -> model/database constraint
        -> safe ActivityLog with same request ID
        -> success or stable error envelope with one request ID
```

Handled API faults keep field/detail shape plus a stable code. API CSRF failures use the same JSON contract. Request bodies stop at 64 KiB and JSON parsing stops after 32 container levels; oversized input returns stable `payload_too_large` HTTP 413 and malformed/deep JSON returns a safe parse error before any write. Unhandled `/api/` faults become safe JSON `server_error` responses with the request ID; raw fault text is not returned. A separate safe fault event records only fault type and source basename/line/function.

Every completed application request emits one structured JSON event with only event name, request ID, method, path, status, and duration. It uses `request.path`, not the query string, and omits bodies, headers, and client IP. A logging sink failure cannot break the response or prevent request-context cleanup.

## URL map

- `/api/v1/auth/login/`, `/logout/`, `/me/`.
- `/api/v1/users/` and role-change action.
- `/api/v1/customers/` and deactivate action.
- `/api/v1/customer-phones/`.
- `/api/v1/leads/` and reassign action.
- `/api/v1/interactions/` read/create only.
- `/api/v1/products/` and deactivate action.
- `/api/v1/sales/` and cancel action.
- Read-only `/api/v1/activity-logs/` for scoped Company IT and Platform Admin access.
- `/api/v1/reports/user-performance/` for scoped JSON metrics.
- `/api/v1/exports/user-performance.xlsx` for the same scoped rows/filters as a workbook.
- `/api/v1/health/live/`, `/health/ready/`, compatibility `/health/`.
- Authenticated `/api/v1/schema/` and `/api/v1/docs/` only outside production. Production does not map either route.
- `/` first-party Persian/RTL Kariz shell and `/admin/` Persian/RTL branded Django admin.

## Role boundary map

| Role | Operational CRM | User administration | Audit read | Report scope |
|---|---|---|---|---|
| Sales Agent | Own/created/assigned scope only | Denied | Denied | Self only |
| Sales Manager | Company operational scope | Denied until Team model and bounds exist | Denied until limited operational scope is defined | All fixed-role current/history users |
| Company IT | Company operational scope, including Product, reassignment, cancellation, and deactivation | Ordinary roles through `company_it`; Platform Admin rows hidden | Snapshot-scoped; Platform Admin and unknown legacy actor/user-target rows hidden | All CRM identities in current/history scope |
| Platform Admin | Full CRM scope | All fixed CRM roles | Full | All fixed-role current/history users |

All four roles remain separate from Django staff, superuser, groups, direct permissions, and server access. Any account holding one of those server-management flags/relations is removed from CRM authentication, list/detail, transition-target, assignment-target, and report scopes even if its stored CRM role is valid.

## Core data flow

```text
User creates Customer
  -> CustomerPhone folded from allowed input and stored as exact ASCII +98 identity
  -> Customer gets one or many Leads
  -> elevated role assigns/reassigns Lead
  -> assignment history and audit append atomically
  -> assigned user records Interaction
  -> assigned/elevated user marks confirmed Sale
  -> Product price must be positive
  -> Sale snapshots product price and computed amount
  -> exact role-scoped report aggregates Customer/Sale rows
  -> same query result renders JSON and XLSX
```

Report flow uses strict offset-aware half-open date filters, optional scoped user and non-enumerating Sale Product filters, three fixed database queries, two-decimal money, `ROUND_HALF_UP` averages, no-store responses, and spreadsheet formula-prefix defense. Query-growth tests also hold the users, activity logs, customers, phones, leads, interactions, products, and sales list routes flat from one to five rows.

## Migration boundary map

- `accounts.0002`: fixed CRM role check.
- `auditlog.0002`: nullable actor/object CRM-role snapshots; legacy rows stay unknown.
- `sales.0004`: Lead assignment fields are all null or all set.
- `sales.0005`: Sale snapshot pairing and arithmetic guards.
- `sales.0006`: preflight, then global active normalized-phone identity.
- `sales.0007`: preflight, then strictly positive Product price.
- `sales.0008`: preflight, then exact ASCII `+98` normalized-phone shape.
- `sales.0009`: bounded-ID preflight, then Customer address at 2,000 characters and five notes/description fields at 4,000; no stored text is copied into errors or rewritten.
- Fast tests apply these migrations on SQLite. Native PostgreSQL zero/upgrade proof remains blocked by missing host tools.

## Deployment topology

```text
Host :80 -> Nginx fixed-host HTTPS redirect
Host :443 -> Nginx TLS + checked HSTS
               -> /static/ from read-only static volume
               -> read-only Gunicorn web:8000
                         -> PostgreSQL app login on backend-only network

One-shot db-bootstrap service:
  wait for DB -> create/repair split roles and rotate credentials
              -> lock one owner/ACL transaction -> exit

One-shot migrate service:
  use migration-owner login -> migrate -> collectstatic -> exit -> db-finalize starts

One-shot db-finalize service:
  rerun role/credential preparation
  -> lock one owner/ACL transaction
  -> apply exact table/sequence/routine policy -> exit -> web may start

Profile-only backup service:
  use read-only backup login -> exact external backup volume
  -> custom dump -> archive check -> SHA-256 sidecar -> atomic final pair
```

- Docker image uses a required digest-qualified Python base input, an exact Python dependency-version lock, non-root Gunicorn, root-owned source, and no writable source tree. Production Compose has no `build:` path and requires digest-qualified application, PostgreSQL, and Nginx references. Real reviewed digest values, package hashes, and built-artifact proof remain external.
- PostgreSQL data and backups use two required explicit external volume names; Compose cannot silently choose project-scoped data or backup volumes.
- Database init superuser, migration owner, runtime application, and read-only backup logins are distinct. Web receives only the application credential and no schema-owner rights.
- Database, bootstrap, migrate, finalizer, backup, and web share the backend-only network. Nginx shares only the frontend network with web. Application and database ports are not host-published. Backup is the seventh base service definition and runs only under its profile; the other six form the normal topology. A separate one-service restore definition has no network.
- Web health checks process liveness; public readiness checks PostgreSQL. Nginx owns an independent edge liveness path.
- All seven service definitions use bounded JSON-file logs. Application and Nginx request logs are structured and query-free; Nginx adds request ID and finite proxy timeouts.
- A reversible Nginx write-stop override rejects POST/PUT/PATCH/DELETE with stable 503 JSON while reads and health remain available.
- Real stack boot, Nginx syntax/routing, certificate/renewal/TLS scan, exact volume reuse, backup destination/policy, and backup/restore execution proof remain unresolved.

## Backup and restore boundary

- `scripts/backup-postgres.ps1` accepts one explicit sentinel-protected root, creates a custom-format dump, validates its archive list, adds a SHA-256 sidecar, and moves same-filesystem temporary files to exact non-overwriting final names.
- Optional age retention is off by default. When approved, it considers only direct exact-name dump/checksum pairs under that root; it never recurses or broadly deletes.
- The profile-only backup job uses the separate read-only login and exact external backup volume. It cannot receive application or migration credentials.
- `scripts/verify-postgres-restore.ps1` accepts only a checksum-matching exact backup under that root and a loopback high-port server. It restores into a new generated `kariz_restore_verify_*` database, uses the shared schema contract, then drops only that generated database in cleanup.
- `compose.restore-verify.yml` and `scripts/verify-postgres-restore.sh` provide the default one-shot drill: no network or database secret, read-only backup mount, bounded tmpfs cluster, exact archive/hash checks, and no business target. Both verifiers use `scripts/verify-postgres-schema.sql`, which returns one boolean for nine tables, three heads, ten constraints, and two partial unique phone indexes.
- Neither script reads `.env` nor accepts a password argument. Authentication stays in the deployment secret mechanism or protected PostgreSQL password file.
- Native PostgreSQL client/runtime tools are absent on this host. No real dump, restore, schedule, retention, alert, recovery-time, or recovery-point proof is claimed.

## External dependencies and integrations

- Runtime Python: Django, REST framework, schema generator, PostgreSQL driver, Gunicorn, and openpyxl for XLSX generation.
- No approved external SMS, telephony, ecommerce, payment, shipping, tax, inventory, or website sync integration.
- No Redis, task queue, microservice, or dynamic permission builder.

## Active UI and language/brand state

- `/` maps to `common/templates/common/home.html` and local `common/static/common/kariz.css`.
- The shell declares Persian/RTL, shows only approved Kariz branding and confirmed product scope, and has no language switch, fake action, remote asset, or external/vendor link.
- Django admin uses Persian framework translation/RTL and first-party Kariz titles from `common/admin.py`. CRM roles remain separate from Django admin access.
- The excluded archive was not inspected, changed, or deleted. It is unserved by this stack; any external use and deletion safety remain unproved.
- Source/render/static tests pass. Real browser, responsive, console/network, Docker, and Nginx UI proof remain external.
- Exact manifests and evidence: `docs/codebase/LANGUAGE_CLEANUP.md` and `docs/codebase/BRANDING_CLEANUP.md`.
