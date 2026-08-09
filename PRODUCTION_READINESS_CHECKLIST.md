# Production readiness checklist

Status: `PASS`, `PARTIAL`, `PENDING`, `BLOCKED_EXTERNAL`, or `BLOCKED_DECISION`. A status needs direct evidence.

## Application and schema

| Gate | Status | Evidence / next proof |
|---|---|---|
| Test-settings system check | PASS | Fresh `python manage.py check --settings=config.test_settings` on 2026-08-10 |
| Production deploy check | PASS | Fresh warnings-fatal `check --deploy` with non-secret safe values exited zero; only the deliberate HSTS subdomain/preload warnings were allowed; real deployment remains external |
| Migration drift | PASS | Fresh no-change result at heads `accounts.0002`, `auditlog.0002`, and `sales.0010` after the Interaction contract migration |
| Zero migrations on PostgreSQL | BLOCKED_EXTERNAL | Native tools absent; run `scripts/test-postgres.ps1` |
| Upgrade migrations on PostgreSQL | BLOCKED_EXTERNAL | Need disposable PostgreSQL upgrade fixture/path |
| Critical DB constraints | PARTIAL | Local suite applies role, global active phone, exact ASCII phone shape, assignment, positive Product price, money, and Sale guards; PostgreSQL proof remains blocked |
| Database readiness | PASS | Public readiness executes `SELECT 1`; fast test exists |
| OpenAPI validation | PASS | Fresh UTF-8 `spectacular --validate --fail-on-warn` passes with the sensitive-action `429` response set and shared assertions |

## Security

| Gate | Status | Evidence / next proof |
|---|---|---|
| Production DEBUG off | PASS | `config/production_settings.py` plus test |
| Secrets from environment | PASS | Production secret guard; `.env.example` has placeholders |
| Strict production environment input | PASS | Required secret/public-host/HTTPS-origin/database-role/TLS fields, strict booleans, bounded ports/timeouts/HSTS, and proxy CIDRs fail closed in tests |
| Ignore secret/key/database artifacts | PASS | Expanded ignores plus exact 134-path worktree policy/name-only high-confidence scan pass; a later reference-bound scan remains SRC-002 |
| Allowed hosts/origins explicit | PASS | Validator accepts only one allowed-host value equal to `KARIZ_PUBLIC_HOST` and one origin exactly `https://KARIZ_PUBLIC_HOST`; wildcards, dot prefixes, siblings, ports, slashes, and extras fail |
| Secure cookies and headers | PARTIAL | Secure cookies forced; direct TLS, fixed-host redirect, and exact edge HSTS config pass source tests; live proof external |
| CSRF/session behavior | PASS | Login, own-profile write, logout, and API JSON CSRF tests pass in the fresh 226-test suite |
| Inactive-user denial | PASS | Login and shared active-user gates pass; wider final route matrix still tracked separately |
| Role/object isolation | PASS | Approved route/filter/direct-ID matrix passes; staff, superuser, group, and direct-permission identities are excluded from CRM scope |
| Privilege fields blocked | PASS | Login extras, `id`, role, staff, superuser, groups, and direct permissions reject in tests |
| Request IDs and audit binding | PASS | Middleware/audit tests and edge config tests |
| Forwarded-header trust | PASS | One proxy in production; Nginx overwrites chain; CIDR-gated audit IP |
| Login throttling | PASS | Application and edge limits with tests/config proof |
| Sensitive endpoint throttling | PASS | User writes, Lead reassignment, Sale create/cancel, audit reads, report JSON, and XLSX use the per-user `sensitive` rate; focused API tests pass, while live edge/runtime proof remains external |
| Audit secret scrubbing | PASS | Safe key/value allowlist and no-leak tests |
| Audit read scope | PASS | Stored role snapshots drive the read-only scope; Company IT cannot see Platform Admin or unknown legacy activity; Manager/Agent fail closed |
| Dependency/source scans | PARTIAL | Hashed Python lock, package consistency, high-confidence source scan, and Docker build base-digest/interpreter/platform gates pass. Compose interpolation proves only nonempty refs; the required validator/release flow rejects missing, mutable, or malformed refs. Real digests, SBOM, and current advisory/container scans remain external |

## API and behavior

| Gate | Status | Evidence / next proof |
|---|---|---|
| Versioned API and pagination | PASS | `/api/v1/`, page-number default |
| Strict unknown/server fields | PASS | Shared mixin and tests |
| Transactional reassignment/history/audit | PASS | Locked service and rollback tests |
| Product/Sale transition security | PASS | Positive Product price, role rights, hidden IDs, snapshots, cancellation, rollback, and conflict paths pass locally |
| Stable machine error codes | PASS | Envelope has stable code/request ID; tests cover validation, parse errors, `payload_too_large` 413, permission, not-found, method, throttle, 409 conflict, and safe detail-free 500 faults |
| Bounded request and free text | PASS | Request bodies stop at 64 KiB, JSON stops at 32 container levels, address stops at 2,000 characters, and five notes/description fields stop at 4,000 before write |
| Interaction input and database contract | PARTIAL | Direction is exact `inbound`/`outbound`; outcome is trimmed, nonblank, and at most 80 characters across serializer/service/model/migration checks; PostgreSQL apply/constraint proof remains external |
| Reports exact formulas | PASS | Half-open period, confirmed Sales only, two-decimal totals, half-up average, zero denominator, and inactive history tests |
| Report role scope and filters | PASS | Agent-self and elevated company scope; safe user denial and non-enumerating Product/date/unknown/repeated/direct-ID tests |
| XLSX parity and workbook validity | PASS | Shared report service, workbook-open/filter parity, exact max-range money text, formula defense, binary schema, and no-store tests |
| List query growth | PASS | One-versus-five-row checks stay flat for users, activity logs, customers, phones, leads, interactions, products, and sales |

## Runtime and operations

| Gate | Status | Evidence / next proof |
|---|---|---|
| Non-root production server image | PASS | Dockerfile uses non-root Gunicorn |
| Compose parses | PARTIAL | Host YAML/topology/log-cap tests pass; Docker `compose config` proof unavailable |
| One-shot database bootstrap/migration/finalize/static source contract | PASS | Init, migration-owner, application, and read-only backup roles are split; role/password prep precedes one locked owner/ACL unit in bootstrap/finalize; migrate is a separate one-shot job |
| Database least-privilege source contract | PARTIAL | Web receives only the application login and exact table/sequence/routine policy; live grants, denied DDL/routine/history mutation, and rollback proof remain Phase 12 |
| Persistent volume source contract | PARTIAL | Compose requires exact external `POSTGRES_DATA_VOLUME` and `POSTGRES_BACKUP_VOLUME` names; exact live mount/reuse/access proof remains Phase 12 |
| Runtime filesystem source contract | PARTIAL | Image source is root-owned and Compose marks web read-only with `/tmp` tmpfs/read-only static; container runtime proof remains Phase 12 |
| Portable bounded throttle cache source | PASS | Production uses a 10,000-entry file cache under the platform temporary root, shared by workers in the one approved web container; scale-out needs an approved shared store and new proof |
| Digest-only production image source | PASS | Production Compose has no `build:` path; interpolation itself requires nonempty refs. The mandatory validator/release flow enforces version plus lowercase SHA-256 digests for all four images, and the Docker build gate checks the base digest, Linux/amd64 platform, and Python 3.13 interpreter |
| Stack boots and health passes | BLOCKED_EXTERNAL | Docker absent |
| Nginx routing/static/errors | BLOCKED_EXTERNAL | Nginx binary/runtime absent |
| Restart policies | PASS | Database, web, and edge policies present |
| Log rotation/bounds | PASS | All seven service definitions, including the profile-only backup job, use 10 MB by 5 JSON-file caps; edge log is bounded by container and omits query/referrer/browser-agent data |
| Application request log contract | PASS | Fixed JSON event/ID/method/path/status/duration fields; query, body, headers, and IP omitted; sink failure cannot break a response; live container output proof remains external |
| Automated backup | PARTIAL | A profile-only job uses the read-only backup role and exact external backup volume; guarded custom-format dump, archive-list check, SHA-256 sidecar, atomic final rename, and optional exact-pair retention exist; destination policy, schedule, owner, and real run remain external/decision work |
| Disposable restore proof | BLOCKED_EXTERNAL | Host and no-network container verifiers share one boolean for nine core tables, three migration heads, twelve constraints, and two partial unique indexes; real PostgreSQL/Docker proof is absent |
| Reversible write-stop source contract | PASS | Exact edge override blocks POST/PUT/PATCH/DELETE with stable 503 JSON while reads and health remain available; live edge proof is Phase 12 |
| Deployment/rollback/runbooks | PASS | Deployment, bootstrap, database-role, TLS, backup/restore, rollback, incident, release, dependency, UAT, load, and security-scan guides exist |
| TLS source contract | PASS | Direct Nginx TLS, fixed public host, HTTP redirect, TLS 1.2/1.3, checked HSTS, certificate mounts, and production settings pass source tests |
| TLS live proof | BLOCKED_EXTERNAL | Need approved hostname/certificate files, renewal path, Nginx runtime, and scanner evidence |

## Product quality and release

| Gate | Status | Evidence / next proof |
|---|---|---|
| Full tests pass | PASS | Fresh full fast suite completed 226 tests successfully; six PostgreSQL-only cases skipped on SQLite as designed |
| Critical path tests pass alone | PARTIAL | Backend/report/UI source tests pass; real browser and stack paths remain external |
| No schema drift | PASS | Fresh dry-run reports no changes at `accounts.0002`, `auditlog.0002`, and `sales.0010` |
| Active-file ledger exactness | PASS | The settled ledger has 179 unique live goal-field rows, exact Phase 1 links, and zero missing, stale, or malformed row |
| No forbidden tracked/shipped artifact | PASS | The exact settled worktree manifest has 134 unique paths: 47 modified, 87 added, zero deleted/renamed, zero forbidden path, zero high-confidence name-only secret match, and no temporary wheel path; reference-bound proof remains SRC-002 |
| Active UI is Persian/RTL only | PARTIAL | Root shell/admin source and render tests pass; real browser/edge proof absent |
| Active UI uses Kariz brand | PARTIAL | Root shell/admin/schema checks pass; real browser/edge link/visual proof absent |
| No open repository P0/P1 | PENDING | The prior audit predates the current backend/operations batches; rerun after full tests, schema, ledger, manifest, and durable-doc reconciliation |
| Known limitations explicit | PASS | The dual blocker register mirrors all 28 BIZ/SRC/EXT/OPS IDs with exact missing inputs and close proof, including BIZ-003 and BIZ-013 |
| Capacity/load proof | BLOCKED_DECISION | Bounded GET-only argument, redirect, output, and loopback tests cover the harness/runbook; BIZ-010 still needs an approved target/tool/workload/threshold/window/owner/abort record |
| Production candidate evidence | PARTIAL | Exact 134-path worktree source, release notes, local gates, and blocker proof exist; final independent P0/P1 audit is pending and SRC-002/OPS-001 still block an immutable deploy/rollback artifact |
| Full production proof | BLOCKED_EXTERNAL | Phase 12 |

Current allowed claim: **work in progress** until the independent final repository audits close the P0/P1 gate. If they pass, State B permits **production candidate; external verification pending** while SRC-002 and all explicit BIZ/EXT/OPS inputs remain blocked. Do not claim production ready or a deployable immutable artifact.

## Complete blocker cross-check

Every business (`BIZ`), source (`SRC`), external (`EXT`), and human operations (`OPS`) item is explicit here and in `BLOCKERS.md`. Command labels below refer to the literal command blocks in [the blocker register](BLOCKERS.md#exact-close-command-sets). A row closes only when its input, command exit codes or signed evidence, UTC time, operator/reviewer, exact release, and exact target are recorded. No secret value may enter proof.

| ID | Readiness state | Exact remaining input | Exact close proof / command |
|---|---|---|---|
| BIZ-001 | BLOCKED_DECISION | Lead assignment rule | Approved rule plus assignment service/API/audit tests and `C-REPO` |
| BIZ-002 | BLOCKED_DECISION | Lead statuses and transitions | Approved matrix plus transition tests, migration review if needed, and `C-REPO` |
| BIZ-003 | BLOCKED_DECISION | Interaction outcome codes and qualifying-call grouping | Approved outcome code/group set plus sales/report/schema tests and `C-REPO` |
| BIZ-004 | BLOCKED_DECISION | Customer/conversion/reassignment KPI formulas | Approved exact formulas plus report/XLSX tests and `C-REPO` |
| BIZ-005 | BLOCKED_DECISION | Team schema and Manager boundary | Approved schema/scope plus migration/direct-ID/filter tests and `C-REPO` |
| BIZ-006 | BLOCKED_DECISION | Sale correction contract | Approved fields/transition/audit rule plus service/API/constraint tests and `C-REPO` |
| BIZ-007 | BLOCKED_DECISION | Human XLSX presentation contract | Approved labels/columns/cell/style/Jalali rules plus workbook/parity tests and `C-REPO` |
| BIZ-008 | BLOCKED_DECISION | Optional after-sales inclusion and workflow | Approved entities/status/access rules plus all-layer tests/schema and `C-REPO` |
| BIZ-009 | BLOCKED_DECISION | Backup path, schedule, retention, owners, alerts, RTO, and RPO | Signed policy and exact scheduler/volume record; run `C-RESTORE` and retain hash/restore/alert proof |
| BIZ-010 | BLOCKED_DECISION | Capacity target, approved health path, workload, bounds, window, owners/abort rules, and tool approval | Run `C-LOAD` or signed exact alternative; retain release/tool/version/UTC/latency/error/resource/abort result and owner acceptance |
| BIZ-011 | BLOCKED_DECISION | Manager audit boundary | Approved object/user/operation scope plus list/direct-ID/filter tests and `C-REPO` |
| BIZ-012 | BLOCKED_DECISION | Legacy audit role source or permanent denial | Approved guarded backfill plus `C-PG`, or signed permanent denial; audit tests and `C-REPO` |
| BIZ-013 | BLOCKED_DECISION | Rule for deactivating a user with active assigned Leads | Approved block/reassign/temporary-owner rule plus locked account/sales/API/audit/history tests and `C-REPO` |
| SRC-001 | PASS | None for current served UI boundary | `C-UI` proof is recorded; reopen on served-topology change |
| SRC-002 | BLOCKED_DECISION | User authorization for one immutable release ref | Run `C-REF`, regenerate/ref-review the source manifest, and run `C-REPO` from the exact artifact |
| EXT-001 | BLOCKED_EXTERNAL | PostgreSQL bin with compatible `initdb`, `pg_ctl`, `psql`, `createdb`, and `pg_dump`, plus compatible Bash | Run `C-PG`; retain full tests, 0004-to-0010 upgrade, bootstrap/finalizer, ACL/denial/dump/failure-rollback/constraint proof |
| EXT-002 | BLOCKED_EXTERNAL | Docker, reviewed digests, and exact approved data/backup volumes | Run recovery-first deploy flow and `C-STACK`; retain config/pull/boot/health/static/API/volume/write-stop proof |
| EXT-003 | BLOCKED_EXTERNAL | Nginx runtime | Run `C-EDGE`; retain redirect/static/rate/timeout/error/request-ID HTTP proof |
| EXT-004 | BLOCKED_EXTERNAL | Hostname, certificate/key, renewal, HSTS choice, and scanner | Run Nginx syntax and exact TLS runbook curl/scanner steps; retain chain/protocol/HSTS/renewal proof |
| EXT-005 | BLOCKED_EXTERNAL | Real backup pair and Docker/PostgreSQL runtime | Run `C-RESTORE`; retain one true nine-table/three-head/twelve-constraint/two-index result |
| EXT-006 | BLOCKED_EXTERNAL | Browser and edge-served UI | Record exact `/` and `/admin/login/` desktop/mobile screenshots, Persian/RTL/Kariz checks, static responses, and clean console/network export |
| EXT-007 | BLOCKED_EXTERNAL | Application/scanner digests, isolated scan host, restricted evidence root, public TLS target/client, owners, retention, and reviewer | Run `C-SCANS`; bind lock hash, tool databases/versions, reports, dispositions, hashes, sealed anchor, and TLS result to the exact release/artifact digests |
| OPS-001 | BLOCKED_DECISION | Stored current and prior immutable artifacts | Record refs/digests, protected location, retrieval and compatibility owner; run `C-REF` for current |
| OPS-002 | BLOCKED_DECISION | Named owners and release window/notice/success/abort rules | Signed change record with all owners, UTC window, notice, success/abort, HSTS/preload, and go/no-go authority |
| OPS-003 | BLOCKED_DECISION | Backup scheduler/overlap/timeout/alerts/off-host/RTO/RPO policy | Signed policy, scheduled `C-RESTORE`, forced/missed alert proof, overlap denial, and owner acceptance |
| OPS-004 | BLOCKED_DECISION | External log retention/access/deletion/alert/evidence policy | Signed policy and sink/access/rotation/alert test tied to request IDs with no sensitive field capture |
| OPS-005 | BLOCKED_DECISION | Existing active Platform Admin or first-install approval | Record existing admin, or run `C-BOOTSTRAP`; retain audit and repeat-denial proof |
| OPS-006 | BLOCKED_DECISION | Write-stop, rollback, incident, cutover, reopen owners and tabletop | Run `C-EDGE`; record times/request IDs/prior-artifact static recovery/health/business/tabletop/reopen sign-off |
