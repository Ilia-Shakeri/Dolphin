# Blockers

Only the affected work is blocked. Independent roadmap work continues.

## Business decisions

| ID | State | Missing decision | Impact | Safe work that continues | Close evidence |
|---|---|---|---|---|---|
| BIZ-001 | BLOCKED_DECISION | Initial Lead assignment method | No automatic assignment/self-pick rule | Manual create plus dedicated elevated assignment/reassignment | Approved assignment rule and tests |
| BIZ-002 | BLOCKED_DECISION | Final Lead statuses/transitions | No status-transition action or enum claim | Lead storage, scope, assignment, reports not needing status | Approved codes and transition matrix |
| BIZ-003 | BLOCKED_DECISION | Final Interaction outcome codes and qualifying-call grouping | No answered/call KPI | Direction is fixed to inbound/outbound; outcome stays bounded free text; sale/customer metrics continue | Approved outcome code set and qualifying metric grouping |
| BIZ-004 | BLOCKED_DECISION | Generic customer KPI, conversion denominator, reassignment history semantics | Those metrics stay absent | Exact created-customer and confirmed-sale metrics | Approved formulas with date/ownership rules |
| BIZ-005 | BLOCKED_DECISION | Team model and manager team-admin scope | Sales Manager cannot administer users | Company IT/Platform Admin user management | Approved Team schema and boundaries |
| BIZ-006 | BLOCKED_DECISION | Sale correction fields and accounting meaning | Correction stays rejected; cancellation works | Sale creation/cancellation/audit | Approved correction transition and audit fields |
| BIZ-007 | BLOCKED_DECISION | Final human-facing XLSX columns/labels, numeric-cell/style choice, and Jalali display | Current export stays a precision-safe machine-readable UTC foundation | Stable identifier columns, exact two-decimal money text, filters sheet, JSON parity | Approved final columns/labels/cell types/style/display rules |
| BIZ-008 | BLOCKED_DECISION | Optional after-sales scope | No support entity/API | Core CRM work | Explicit inclusion and workflow/status rules |
| BIZ-009 | BLOCKED_DECISION | Backup destination, schedule, retention, owners, alerts, RTO, and RPO | Cannot claim live backup or recovery policy | Fail-closed scripts/config/runbook with placeholders | Signed policy plus real scheduled backup, alert, checksum, and disposable restore proof |
| BIZ-010 | BLOCKED_DECISION | Exact capacity target, approved health path, workload, thresholds, window, owners, abort rules, and approval of the bounded repository harness or another named tool | No final sizing/load claim | Query review plus the fail-closed GET-only harness and runbook | Signed target/tool record and production-shaped `C-LOAD` result |
| BIZ-011 | BLOCKED_DECISION | Sales Manager limited operational-audit visibility | Manager audit API stays denied; broad access would leak unrelated activity | Company IT scoped audit and Platform Admin full audit | Approved operation/object/user boundary plus direct-ID tests |
| BIZ-012 | BLOCKED_DECISION | Visibility or authoritative role-at-action source for audit rows created before role snapshots | Company IT cannot view legacy rows with unknown actor/object roles | Platform Admin full view plus fail-closed blank snapshots; new rows store exact snapshots | Approved authoritative backfill source or explicit acceptance of permanent Company IT denial for legacy rows |
| BIZ-013 | BLOCKED_DECISION | Deactivation rule for a user who still owns active assigned Leads: reject deactivation, require prior explicit reassignment, or allow a temporary inactive assignee | An inactive assignee can no longer work those Leads; silently moving them would invent ownership and history | Current behavior preserves the exact Lead assignee and assignment history, performs no implicit reassignment, and leaves explicit audited reassignment to an elevated operator | Approved rule and transition/audit contract; then account plus sales service/API tests prove the chosen behavior and no silent history rewrite |

The approved Phase 5 foundation is complete: `customers_created_count`, `sales_count`, `sales_amount`, `average_sale_amount`, safe date/user/Product filters, role scoping, and JSON/XLSX parity. BIZ-003, BIZ-004, and BIZ-007 block only the undefined metrics or final presentation named in those rows. BIZ-013 forbids any guessed implicit Lead move: current rows keep their exact assignee/history until an elevated operator performs an explicit audited reassignment or an approved deactivation rule replaces that behavior.

## Repository and UI boundary

- SRC-001 is closed for the repository-controlled stack: `/` uses the first-party `common` template/static shell, Django admin is the second active UI surface, and both have Persian/RTL/Kariz source-render tests.
- The excluded static archive remains untouched and unserved by this stack. That does not prove it has no unknown external consumer, so broad archive deletion remains unauthorized without a new exact manifest and runtime evidence.
- SRC-002 has one user-created pushed checkpoint: `8f3c540efe7c1e1f80f31e0a1d991d0328dfe62e`, equal to `origin/main`, with an exact 134-path delta from the durable base. The later 25-path backend/operations audit and durable-evidence overlay is not in that reference. Automatic commit remains forbidden; the combined final candidate needs one new user-created reference and reference-bound rerun. State B uses only `production candidate; external verification pending`.

## External environment

| ID | State | Missing input/tool | Impact | Close evidence |
|---|---|---|---|---|
| EXT-001 | BLOCKED_EXTERNAL | Approved PostgreSQL bin path containing compatible `initdb`, `pg_ctl`, `psql`, `createdb`, and `pg_dump`, plus an approved compatible Bash executable | Cannot run full PostgreSQL tests, the 0004-to-0010 upgrade, role bootstrap/finalizer, exact ACL/denials, dump, failure rollback, or target-engine constraints | Run `C-PG`; retain full test, upgrade, bootstrap/finalizer, ACL/denial, dump, rollback, and constraint exit proof |
| EXT-002 | BLOCKED_EXTERNAL | Docker runtime, reviewed digest-qualified images, and approved exact external data/backup volume mappings | Cannot pull/boot the digest-only stack or prove the intended persistent data and backup volumes are mounted without blank replacement | Compose config/pull/up/health/static/API/write-stop logs plus exact external data/backup volume inspect/mount proof |
| EXT-003 | BLOCKED_EXTERNAL | Nginx runtime | Cannot execute proxy config/error/rate/static smoke | Config test and HTTP evidence through edge |
| EXT-004 | BLOCKED_EXTERNAL | Live direct-Nginx TLS host, approved certificate/key files, and renewal path | Cannot prove HTTPS, HSTS, certificate chain/renewal, or live capacity | Approved deploy, renewal check, and TLS smoke/scanner evidence |
| EXT-005 | BLOCKED_EXTERNAL | Docker/PostgreSQL runtime for a real dump and disposable restore | Guarded profile backup and no-network restore source exist, but no real archive/restore proof can run | Backup plus restore with one true result for nine core tables, three migration heads, twelve constraints, two partial unique indexes, and approved data checks |
| EXT-006 | BLOCKED_EXTERNAL | Real browser and edge-served UI runtime | Cannot prove responsive rendering, console/network cleanliness, static delivery, or visible brand/language through the deployed edge | Browser smoke at `/` and `/admin/login/` across target viewports through Nginx |
| EXT-007 | BLOCKED_EXTERNAL | Exact application, PostgreSQL, Nginx, Python build-base, and five scanner digests; clean isolated scan/build host; restricted evidence root; public TLS target/client; and security reviewer | Hashed Python lock and Docker build digest/interpreter/platform gates exist. Compose interpolation proves only nonempty values; the required validator/release flow rejects mutable or malformed refs. No real runtime image, per-image SBOM/vulnerability result, source-to-image build record, scanner execution, or TLS scan is proven | Run `C-SCANS`; evidence binds the lock hash, source/build record, all runtime/build/scanner digests, per-runtime SBOM/findings, tool databases/versions, TLS result, review, and sealed metadata/anchor to the exact release |

## Missing historical evidence

- The older named backend prompt and frontend context files are absent under canonical or obvious suffixed root names. Current `BACKEND_SPEC.md`, the first-party active shell, and durable goal cover independent work. If those files arrive later, reconcile conflicts without overwriting current evidence or assuming the excluded archive is active.

## Exact close command sets

Use these labels in the complete register below. Commands run only after the named human input and safe target exist. They never authorize a real deploy, database change, credential read, or release commit.

`C-REPO` - repository-controlled release gates:

```powershell
git status --short
git diff --check
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py test --settings=config.test_settings -v 1
python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
python -m pip check
```

`C-UI` - repository UI proof:

```powershell
python manage.py test common.tests.test_ui --settings=config.test_settings -v 1
python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
```

`C-PG` - isolated PostgreSQL proof after the approved bin holds compatible `initdb`, `pg_ctl`, `psql`, `createdb`, and `pg_dump`, and an approved compatible Bash executable exists:

```powershell
$approvedPostgresBin = Read-Host 'Approved PostgreSQL bin path'
$approvedBash = Read-Host 'Approved Bash executable path'
.\scripts\test-postgres.ps1 -PostgresBin $approvedPostgresBin -BashCommand $approvedBash
```

`C-STACK` - protected target stack proof, in the recovery-first order in `docs/ops/DEPLOYMENT.md`:

```powershell
docker compose config --quiet
docker compose -f compose.yml -f compose.write-stop.yml config --quiet
docker compose -f compose.restore-verify.yml --profile restore-verify config --quiet
python scripts/validate_release_images.py
docker compose pull
docker compose up -d
docker compose ps
```

`C-RESTORE` - one real backup and no-network disposable restore after the approved volume and policy exist:

```powershell
docker compose --profile backup run --rm backup
$approvedArchive = Read-Host 'Exact archive leaf printed by the successful backup job'
docker compose -f compose.restore-verify.yml --profile restore-verify run --rm --no-deps restore-verify $approvedArchive
```

`C-EDGE` - edge syntax, health, and reversible write-stop proof on the approved target:

```powershell
docker compose exec -T nginx nginx -t
docker compose -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# kariz-write-stop: on' /etc/nginx/write-stop.conf
docker compose -f compose.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml exec -T nginx grep -F '# kariz-write-stop: off' /etc/nginx/write-stop.conf
```

`C-LOAD` - bounded read-only health load proof only after BIZ-010 records the exact release, HTTPS or loopback origin, repeated host, one allowlisted health path, workload, thresholds, target owner, capacity owner, UTC window, observer, abort authority, error/resource limits, and tool approval:

```powershell
$approvedBaseUrl = Read-Host 'Exact approved HTTPS origin, or loopback HTTP origin'
$confirmedHost = Read-Host 'Repeat the exact lowercase host only'
$approvedPath = Read-Host 'Exact allowed health path'
$approvedRequests = Read-Host 'Approved request count'
$approvedConcurrency = Read-Host 'Approved concurrency'
$approvedTimeout = Read-Host 'Approved per-request timeout seconds'
$approvedWall = Read-Host 'Approved whole-run wall limit seconds'
$approvedP95 = Read-Host 'Approved maximum p95 milliseconds'
$approvedRate = Read-Host 'Approved minimum successful requests per second'
python scripts/load_readiness.py `
  --sentinel KARIZ_READ_ONLY_LOAD_V1 `
  --base-url $approvedBaseUrl `
  --confirm-host $confirmedHost `
  --path $approvedPath `
  --requests $approvedRequests `
  --concurrency $approvedConcurrency `
  --timeout-seconds $approvedTimeout `
  --max-wall-seconds $approvedWall `
  --max-p95-ms $approvedP95 `
  --min-requests-per-second $approvedRate
if ($LASTEXITCODE -ne 0) { throw 'Read-only readiness load gate failed.' }
```

`C-SCANS` - after EXT-007 records the exact commit, application/PostgreSQL/Nginx runtime digests, Python build-base digest, five scanner digests, isolated scan/build host, restricted external evidence root, public hostname/client, owners, retention, and reviewer, execute every command in `docs/ops/SECURITY_SCANS.md` from its clean approved checkout. Retain the reduced source report, locked-dependency report, source-to-image build record, per-runtime SBOM/vulnerability reports, TLS reports, tool/database metadata, exit codes, reviewer dispositions, sealed metadata, integrity manifest, and out-of-band anchor. Repository parsing cannot close this external gate.

`C-REF` - exact reference proof only after explicit user authorization creates or names that reference:

```powershell
$approvedReleaseRef = Read-Host 'Approved immutable release reference'
git rev-parse --verify $approvedReleaseRef
git show --no-patch --format='%H %s' $approvedReleaseRef
git diff --name-status 50a978abc206e43032ce96b36dc0433366198e60 $approvedReleaseRef
```

`C-BOOTSTRAP` - first-install access only after explicit first-install approval:

```powershell
$approvedUsername = Read-Host 'Approved username'
docker compose exec web python manage.py bootstrap_platform_admin --username $approvedUsername
```

## Complete State B blocker register

This is the canonical dual-file register. `PRODUCTION_READINESS_CHECKLIST.md` mirrors every ID. A decision closes only with an approved written rule plus the named proof. An external item closes only with command exit codes, UTC time, operator/reviewer, exact release and target IDs, and the stated evidence. Secret values never enter evidence.

| ID | State | Exact missing input | Exact close proof / command |
|---|---|---|---|
| BIZ-001 | BLOCKED_DECISION | Lead assignment rule | Approved rule, implementation/migration review if needed, focused assignment tests, then `C-REPO` |
| BIZ-002 | BLOCKED_DECISION | Lead status codes and transition matrix | Approved matrix, service/API/audit tests, migration review if needed, then `C-REPO` |
| BIZ-003 | BLOCKED_DECISION | Interaction outcome codes and qualifying-call grouping | Approved outcome codes/grouping, sales/report tests, schema validation, then `C-REPO` |
| BIZ-004 | BLOCKED_DECISION | Customer/conversion/reassignment KPI formulas | Approved numerator, denominator, date, and ownership rules; deterministic report/XLSX tests; then `C-REPO` |
| BIZ-005 | BLOCKED_DECISION | Team schema and manager administration boundary | Approved schema/scope, migration and direct-ID/filter tests, then `C-REPO` |
| BIZ-006 | BLOCKED_DECISION | Sale correction meaning and allowed fields | Approved transition/audit contract, service/API/constraint tests, then `C-REPO` |
| BIZ-007 | BLOCKED_DECISION | Human XLSX labels, columns, cell types, style, and Jalali rule | Approved presentation contract, workbook-open/parity/formula tests, then `C-REPO` |
| BIZ-008 | BLOCKED_DECISION | Optional after-sales inclusion and workflow | Explicit inclusion plus entities/status/access rules, all-layer tests/schema, then `C-REPO` |
| BIZ-009 | BLOCKED_DECISION | Backup destination, schedule, retention, owners, alerts, RTO, and RPO | Signed policy plus exact volume/scheduler record; run `C-RESTORE`; record archive/hash/restore result and alert proof |
| BIZ-010 | BLOCKED_DECISION | Exact capacity target, approved health path, workload, latency/error/resource bounds, UTC window, owners/abort rules, and approval of the repository harness or another named tool | Run `C-LOAD` or the signed exact alternative; record release/tool/version/command, production-shaped target, UTC run, latency/errors/resources, abort outcome, and owner acceptance |
| BIZ-011 | BLOCKED_DECISION | Manager audit object/user/operation boundary | Approved scope, list/direct-ID/filter denial tests, then `C-REPO` |
| BIZ-012 | BLOCKED_DECISION | Legacy audit role source or permanent Company IT denial | Approved source plus guarded migration/tests and `C-PG`, or signed permanent-denial decision plus audit tests; then `C-REPO` |
| BIZ-013 | BLOCKED_DECISION | Assigned-Lead owner deactivation rule | Approved block/reassign/temporary-owner rule, locked service/API/audit/history tests, then `C-REPO` |
| SRC-001 | CLOSED | None for current repository-controlled UI boundary | `C-UI`; route/static/image-boundary evidence already recorded; reopen only if served topology changes |
| SRC-002 | BLOCKED_DECISION | User-created final reference containing the post-`8f3c540` audit/evidence overlay | After the user creates it, run `C-REF`, regenerate the exact base-to-final source manifest, review ref paths, then run `C-REPO` from that artifact |
| EXT-001 | BLOCKED_EXTERNAL | Approved PostgreSQL bin with compatible `initdb`, `pg_ctl`, `psql`, `createdb`, and `pg_dump`, plus approved compatible Bash | Run `C-PG`; retain full PostgreSQL tests, 0004-to-0010 upgrade, bootstrap/finalizer, exact ACL/denials, dump, failure rollback, and target-engine constraint results |
| EXT-002 | BLOCKED_EXTERNAL | Docker runtime, reviewed image digests, and approved exact data/backup volumes | Run recovery-first deploy steps and `C-STACK`; retain config/pull/start/health/static/API/volume/write-stop proof |
| EXT-003 | BLOCKED_EXTERNAL | Nginx runtime | Run `C-EDGE`; also record fixed-host redirect, static, rate, timeout, safe error, and matching request-ID HTTP results |
| EXT-004 | BLOCKED_EXTERNAL | Approved hostname, certificate/key, renewal path, HSTS decision, and TLS scanner | Run Nginx syntax plus exact `docs/ops/TLS.md` curl/scanner commands; retain chain, protocol, redirect, HSTS, renewal, and scanner evidence |
| EXT-005 | BLOCKED_EXTERNAL | Docker/PostgreSQL runtime and a real approved backup pair | Run `C-RESTORE`; retain one true shared-schema result for nine tables, three heads, twelve constraints, and two partial indexes |
| EXT-006 | BLOCKED_EXTERNAL | Real browser and edge-served UI | At `/` and `/admin/login/`, record approved desktop/mobile viewport screenshots, Persian/RTL/Kariz checks, static responses, and clean console/network export |
| EXT-007 | BLOCKED_EXTERNAL | Reviewed application/PostgreSQL/Nginx runtime digests, Python build-base digest, five scanner digests, isolated scan/build host, restricted evidence root, public TLS target/client, owners, retention, and reviewer | Run `C-SCANS`; record source/build identity, lock hash, per-runtime SBOM/findings, tool/database versions, UTC times, exit codes, dispositions, sealed metadata/report hashes, and out-of-band anchor |
| OPS-001 | BLOCKED_DECISION | Current and prior immutable release artifacts stored outside the live worktree | Record both refs/digests, protected location, compatibility owner, and retrieval check; run `C-REF` for the current ref |
| OPS-002 | BLOCKED_DECISION | Named release, database, security, business, rollback, and evidence owners plus window/notice/success/abort rules | Signed change record with names, UTC window, user notice, success window, abort thresholds, HSTS/preload choice, and go/no-go authority |
| OPS-003 | BLOCKED_DECISION | Backup scheduler identity, overlap lock, timeout, missed-run/failure alerts, off-host copy, RTO, and RPO | Signed schedule/policy, one scheduled `C-RESTORE` cycle, forced failure alert, missed-run alert, overlap rejection, and owner acceptance |
| OPS-004 | BLOCKED_DECISION | External application/edge/database log retention, access, deletion, alert, and evidence-store rules | Signed policy plus sink/access/rotation/alert test tied to request IDs; prove no query/body/header/secret capture |
| OPS-005 | BLOCKED_DECISION | Existing active Platform Admin confirmation or explicit first-install bootstrap approval | Record existing active admin, or run `C-BOOTSTRAP`; retain safe audit and second-run refusal proof |
| OPS-006 | BLOCKED_DECISION | Edge write-stop, rollback, incident, recovery-cutover, and reopen owners plus tabletop approval | Run `C-EDGE`; record on/off UTC times, request IDs, prior-artifact/static recovery, health/business checks, tabletop result, and reopen sign-off |
