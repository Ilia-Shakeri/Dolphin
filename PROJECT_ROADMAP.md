# Kariz CRM production roadmap

Last checkpoint: 2026-08-10. This file is the live execution source. A checked task needs evidence before phase status becomes `VERIFIED`.

Status values: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `VERIFIED`.

## Phase summary

| Phase | Title | Status | Next gate |
|---|---|---|---|
| 0 | Repository safety and reproducible baseline | VERIFIED | Keep later commits behind the same review and scan gates |
| 1 | Architecture and codebase mastery | VERIFIED | Keep the exact 179-row ledger and 134-path manifest aligned with later changes |
| 2 | Core schema and migration integrity | DONE | Run zero and upgrade migration proof on PostgreSQL in Phase 12 |
| 3 | Authentication, authorization, audit, request security | VERIFIED | Keep the tested role wall and fail-closed blocks intact |
| 4 | Services and versioned REST APIs | VERIFIED | Keep route, throttle, error, and schema contracts aligned |
| 5 | Predefined reports and XLSX | VERIFIED | Keep undefined metrics/presentation excluded until approved |
| 6 | Persian-only active application cleanup | DONE | Run real browser and edge UI smoke when runtime exists |
| 7 | Kariz rebranding | DONE | Run real browser and edge brand/link smoke when runtime exists |
| 8 | Production configuration and container stack | DONE | Prove digest pulls, boot, routing, static, write-stop, and health in Phase 12 |
| 9 | Database operations, backup, restore, observability | DONE | Run the guarded backup/restore path and approve live policy |
| 10 | Security, reliability, performance verification | DONE | Runtime/load proof remains Phase 12 |
| 11 | Documentation, UAT, release candidate | IN_PROGRESS | Await final independent P0/P1 audit; immutable artifact remains SRC-002 human input |
| 12 | Production environment proof | BLOCKED | Need native/runtime host, hostname, and certificate path |

## Phase 0 - Repository safety and reproducible baseline

- Status: `VERIFIED`
- Objective and scope: Canonical sources, safe ignore rules, local rollback point, dependency/runtime inventory, and clean baseline gates.
- Dependencies: None.
- Files/modules: root source docs, `.gitignore`, `.dockerignore`, Git metadata, requirements, test settings.
- Deliverables:
  - [x] Confirm repository root and Django project.
  - [x] Find authoritative `BACKEND_SPEC.md`.
  - [x] Expand secret, database, backup, log, cache, and generated-output ignores.
  - [x] Run initial tracked high-confidence secret/path scan.
  - [x] Review staged manifest and create safe baseline commit.
  - [x] Record fresh full baseline checks after source reconciliation.
- Migration/data impact: None.
- Security/authorization impact: Prevent secret and generated artifact tracking; no runtime permission change.
- Test plan: Git path/secret scans, `git diff --check`, dependency check, Django check, migration drift, full tests, schema validation.
- Entry criteria: Current workspace accessible.
- Exit criteria: Canonical sources tracked, clean baseline commit exists, scans and baseline commands have evidence. Met by commit `50a978a` and checkpoint 002 checks.
- Verification commands: `git status --short`; targeted `git ls-files`; `git grep`; Django check, migration drift, tests, schema validation.
- Rollback/recovery: Revert only reviewed documentation/ignore patch; never clean or reset broadly.
- Risks/blockers: Existing initial commit may contain large template artifacts; review by manifest, not blind deletion.
- Evidence: `docs/backend/DISCOVERY.md`, `WORKLOG.md`, initial commit `ef1c7f4`, durable baseline commit `50a978a`.

## Phase 1 - Architecture and codebase mastery

- Status: `VERIFIED`
- Objective and scope: Durable map and bounded file-by-file review of active first-party backend and actual served UI.
- Dependencies: Phase 0 safe baseline before deletion work.
- Files/modules: Django apps, config, deployment files, active templates/static entry points, backend docs.
- Deliverables:
  - [x] Keep entity and relation documents separate.
  - [x] Create `CODEBASE_MAP.md` and `FILE_REVIEW_LEDGER.md`.
  - [x] Review backend subsystem batches and link tests/routes.
  - [x] Prove active frontend/template/static entry points for the repository-controlled stack.
  - [x] Regenerate the final current-worktree source manifest and re-prove all 179 current scoped ledger rows after active batches and safe temporary-artifact cleanup finish.
- Migration/data impact: None.
- Security/authorization impact: Finds unguarded entry points and unsafe legacy surfaces.
- Test plan: Import/URL checks, template/static reference checks, active-path smoke tests.
- Entry criteria: Phase 0 baseline exists for any deletion.
- Exit criteria: All active first-party files have exact goal-field ledger rows and roadmap links; runtime/data/request flow map is complete. Met by the exact 179-row schema/link parser and 134-path worktree manifest. Immutable release identity remains SRC-002 human input.
- Verification commands: targeted `git ls-files`, `rg -n`, Django URL/schema checks, bounded template reference checks.
- Rollback/recovery: Documentation-only until exact deletion manifests exist.
- Risks/blockers: Static archive is excluded and unserved by the current stack but may have an unknown external consumer; do not inspect/delete it by guess. Real browser proof is external.
- Evidence: `CODEBASE_MAP.md`, 179 unique live goal-field rows with 179 exact Phase 1 links in `FILE_REVIEW_LEDGER.md`, the exact 134-path `docs/ops/SOURCE_MANIFEST.md`, backend catalogs, and language/branding cleanup manifests.

## Phase 2 - Core schema and migration integrity

- Status: `DONE`
- Objective and scope: User, Customer/phone, Lead/history, Interaction, Product, Sale, and ActivityLog schema with confirmed constraints and clean migrations.
- Dependencies: Authoritative specification and migration inventory.
- Files/modules: `accounts/models.py`, `sales/models.py`, `auditlog/models.py`, migrations, model/workflow tests.
- Deliverables:
  - [x] Custom user and fixed role database guard.
  - [x] Lead assignment all-or-none guard.
  - [x] Sale state, money, snapshot-pair, and total arithmetic guards.
  - [x] Phone normalization and one active primary per Customer.
  - [x] Replace per-Customer active phone uniqueness with confirmed global active identity rule.
  - [x] Require a strictly positive Product price in validation and the database.
  - [x] Require canonical normalized phones to use the exact ASCII `+98` shape in service and database guards.
  - [x] Store role-at-action snapshots through the append-oriented application flow; leave legacy values unknown and fail closed for Company IT.
  - [x] Bound Customer address at 2,000 characters and five notes/description fields at 4,000 with service/API checks and a fail-closed migration preflight.
  - [ ] Apply migrations from zero and upgrade path on isolated PostgreSQL.
- Migration/data impact: `sales.0006`, `sales.0007`, `sales.0008`, `sales.0009`, and `sales.0010` fail closed on conflicting active phones, non-positive prices, non-canonical stored phones, over-limit stored text, or invalid Interaction direction/outcome rows. `auditlog.0002` adds nullable role snapshots without unsafe legacy inference. No migration deletes or rewrites business rows.
- Security/authorization impact: Prevent duplicate identities and malformed workflow ownership at database boundary.
- Test plan: SQLite fast guards plus isolated PostgreSQL migration/constraint suite.
- Entry criteria: Model rules reconciled with `BACKEND_SPEC.md`.
- Exit criteria: No drift; zero/upgrade migrations pass on PostgreSQL; all critical constraints proven.
- Verification commands: migration drift, full tests, `scripts/test-postgres.ps1` with native tools.
- Rollback/recovery: Additive migration with reversible constraint operations; preflight invalid rows before apply.
- Risks/blockers: Native PostgreSQL tools absent on current host; current data conflicts must never be auto-dropped.
- Evidence: migration heads `accounts.0002_user_role_constraint`, `auditlog.0002_activitylog_role_snapshots`, and `sales.0010_interaction_contract`; fresh focused tests and migration-drift proof pass. The fresh full suite and PostgreSQL zero/upgrade proof remain pending.

## Phase 3 - Authentication, authorization, audit, and request security

- Status: `VERIFIED`
- Objective and scope: Session/CSRF, inactive-user denial, exact role/object matrix, safe audit, request IDs, proxy trust, and throttling.
- Dependencies: Phases 1-2 maps and schema.
- Files/modules: account/sales permissions, selectors, services, views, middleware, audit service, Nginx, security tests.
- Deliverables:
  - [x] Login/logout/me and CSRF tests.
  - [x] Fail-closed unknown roles and scoped relations.
  - [x] Password validation and server-field rejection.
  - [x] Request ID and trusted-proxy audit binding.
  - [x] Login throttling at app and edge.
  - [x] Reconcile Company IT operational rights with the current access matrix.
  - [x] Keep Sales Manager user administration and broad user-directory access denied while Team scope is unresolved.
  - [x] Add read-only audit access for Company IT and Platform Admin with Platform Admin activity hidden from Company IT.
  - [x] Complete role-by-route, direct-ID, server-managed identity, and filter/query attack matrix for approved routes.
  - [x] Prevent the final active Platform Admin from demotion or deactivation under a race-safe lock.
  - [x] Keep Django staff, superuser, group, and direct-permission accounts outside every CRM identity scope.
- Migration/data impact: `auditlog.0002` adds nullable actor/object role snapshots without guessing legacy roles. No audit row is rewritten.
- Security/authorization impact: Direct access control and audit integrity.
- Test plan: Every role across list/retrieve/write/action, inactive users, CSRF, direct IDs, hidden relation IDs, spoofed forwarding headers.
- Entry criteria: Scoped selectors and services mapped.
- Exit criteria: Matrix tests prove every endpoint and action; no unresolved P0/P1 access defect.
- Verification commands: targeted account/sales/common tests, full suite, schema permission review.
- Rollback/recovery: Small selector/permission/service changes with focused tests.
- Risks/blockers: Sales Manager team-user scope and limited operational-audit scope remain unresolved; both stay denied rather than broad. BIZ-013 leaves assigned Leads on the exact inactive owner with history intact and forbids guessed implicit reassignment until an owner-deactivation rule is approved.
- Evidence: request-context/logging tests, account security tests, audit/report scope tests, sales workflow/API tests, and the fresh 226-test full fast suite on 2026-08-10; six PostgreSQL-only tests skipped on SQLite.

## Phase 4 - Services and versioned REST APIs

- Status: `VERIFIED`
- Objective and scope: All approved features have matching service, validation, scoped API, errors, audit, schema, and tests.
- Dependencies: Phases 2-3.
- Files/modules: services, serializers, views, URLs, exception handling, schema docs/tests.
- Deliverables:
  - [x] Versioned auth, users, customers, phones, leads/reassign, interactions, products, sales/cancel, audit, reports, health, and non-production schema/docs.
  - [x] Locked transitions and append-only interaction API.
  - [x] Search/order/pagination and documented status filters.
  - [x] Add stable machine-readable error codes and request IDs without leaking object existence.
  - [x] Return safe JSON `server_error` for unhandled API faults without response detail leakage.
  - [x] Use HTTP 409 for confirmed duplicate/no-op conflicts, including username, phone, SKU, unchanged role/assignment, and repeated cancellation/deactivation.
  - [x] Add approved read-only audit access for Company IT and Platform Admin; defer undefined Sales Manager audit granularity.
  - [x] Reconcile cancellation status/error/schema behavior.
  - [x] Apply the user-keyed sensitive throttle to user writes, Lead reassignment, Sale create/cancel, audit reads, report JSON, and XLSX paths.
  - [x] Refresh generated-schema `429` assertions and run the fresh full suite.
  - [ ] Implement Sale correction only after its fields and accounting meaning are approved.
- Migration/data impact: None expected.
- Security/authorization impact: Object scopes and mutation gates remain server-enforced.
- Test plan: route-method matrix, validation shape/codes, schema actions/errors/examples, service rollback.
- Entry criteria: Current spec-to-route gap list complete.
- Exit criteria: Every approved backend capability has all layers and a freshly validated schema. Met for repository scope; runtime proof remains Phase 12.
- Verification commands: full tests, schema validation, URL/method inspection, targeted workflow tests.
- Rollback/recovery: Revert one route/service batch; migrations not expected.
- Risks/blockers: Sale correction details and Sales Manager audit visibility granularity are explicit decision blocks; approved routes remain complete without them.
- Evidence: `docs/backend/API_CONTRACT.md`, audit/report/error/request-limit tests, production docs-route removal tests, 97 focused backend tests, the fresh 226-test full suite, and UTF-8 warnings-fatal generated-schema validation.

## Phase 5 - Predefined reports and XLSX

- Status: `VERIFIED`
- Objective and scope: Exact user-performance metrics, safe date/user/product filters, role scope, and matching XLSX.
- Dependencies: Phases 2-4; exact metrics in specification.
- Files/modules: `reports/`, routes, schema, requirements, tests, report docs.
- Deliverables:
  - [x] `customers_created_count`, `sales_count`, `sales_amount`, `average_sale_amount`.
  - [x] Half-open offset-aware date range plus authorized user and Sale-only Product filters.
  - [x] JSON endpoint and XLSX export with identical scoped query result.
  - [x] Two-decimal money, `ROUND_HALF_UP` average, zero-denominator behavior, and deterministic fixtures.
  - [x] Unknown/repeated/filter-attack, fixed-query-count, OpenAPI, workbook-open, formula-defense, and no-store tests.
- Migration/data impact: None expected; proven query indexes only if needed.
- Security/authorization impact: Agents own scope; Manager, Company IT, and Platform Admin company/user scope.
- Test plan: exact formulas, cancelled-sale exclusion, date boundaries, user scope, ID/filter attacks, JSON/XLSX parity.
- Entry criteria: Current authorization matrix reconciled.
- Exit criteria: Exact metrics and exports pass deterministic tests and schema validation.
- Verification commands: report test module, full suite, schema validation, workbook load.
- Rollback/recovery: Remove isolated report routes/code; no business data mutation.
- Risks/blockers: Generic customer count, conversion, outcome grouping, final human-facing columns/style, and Jalali display remain blocked and excluded. Current XLSX is a machine-readable foundation.
- Evidence: `BACKEND_SPEC.md`, `docs/backend/API_CONTRACT.md`, `reports/`, report tests, the fresh 226-test suite, and current validated schema.

## Phase 6 - Persian-only active application cleanup

- Status: `DONE`
- Objective and scope: Prove active UI, preserve Persian/RTL, remove active language selection and unused locale resources safely.
- Dependencies: Phase 0 rollback baseline and Phase 1 active-path map.
- Files/modules: active templates, first-party scripts/static, settings, locale manifest.
- Deliverables:
  - [x] Create `docs/codebase/LANGUAGE_CLEANUP.md` and active-path manifest.
  - [x] Set explicit Persian default and RTL behavior.
  - [x] Prove the active first-party shell has no language switch UI/state behavior.
  - [x] Review the active slice for locale deletion candidates; none exist, so delete nothing.
  - [x] Template render and static-finder/collectstatic evidence.
  - [ ] Real browser, responsive, console/network, and edge smoke evidence.
- Migration/data impact: None unless a dormant profile language field is found; removal needs migration review.
- Security/authorization impact: Avoid unsafe query/cookie locale behavior; no role change.
- Test plan: template render, static collection/build, reference no-match, browser routes and console/network smoke.
- Entry criteria: Active UI entry point proven; Git rollback baseline present.
- Exit criteria: Active app is Persian/RTL only; no switch path or broken locale reference.
- Verification commands: targeted reference scans, template tests, static/build check, browser smoke.
- Rollback/recovery: Small exact deletion groups restored from Git if any reference breaks.
- Risks/blockers: The excluded archive is unserved by the current stack but remains untouched; real browser/edge proof is external.
- Evidence: `docs/codebase/LANGUAGE_CLEANUP.md`, UI tests, static dry run, full suite.
- Repository completion checkpoint: 2026-08-09, Goal checkpoint 003; source/render proof passed again in the 226-test gate on 2026-08-10. Browser/edge proof remains external.

## Phase 7 - Kariz rebranding

- Status: `DONE`
- Objective and scope: Kariz identity on all active user/project surfaces without breaking stable theme symbols or notices.
- Dependencies: Phase 1 and active UI map; Phase 0 rollback baseline.
- Files/modules: active templates/static, admin config, schema metadata, docs, deployment metadata.
- Deliverables:
  - [x] Create `docs/codebase/BRANDING_CLEANUP.md` and exact active-path manifest.
  - [x] Set Kariz branding on the first-party root shell, admin, and schema title.
  - [x] Prove the active shell has no visible vendor/demo/external links or fake actions.
  - [x] Add active-path brand tests with archive/framework boundaries.
  - [x] Preserve archive and required third-party notices without blind replacement.
  - [ ] Real browser, responsive, link, console/network, and edge smoke evidence.
- Migration/data impact: None.
- Security/authorization impact: Remove unsafe external demo/upload links.
- Test plan: active-path text/link scan, template/static/browser smoke, admin/schema title checks.
- Entry criteria: Active surfaces classified.
- Exit criteria: No user-visible vendor brand/demo links; residual terms justified and not visible.
- Verification commands: policy test, targeted scans, render/build/browser checks.
- Rollback/recovery: Reference-aware small edits; stable runtime symbols unchanged.
- Risks/blockers: Excluded vendor/minified/archive files are not active in the current stack and were not edited; browser/edge proof is external.
- Evidence: `docs/codebase/BRANDING_CLEANUP.md`, UI/admin/schema tests, static dry run.
- Repository completion checkpoint: 2026-08-09, Goal checkpoint 003; source/render proof passed again in the 226-test gate on 2026-08-10. Browser/edge proof remains external.

## Phase 8 - Production configuration and container stack

- Status: `DONE`
- Objective and scope: Secure settings, least-privilege image, migration job, static serving, health, proxy, restart, and environment validation.
- Dependencies: Phases 2-4 for application runtime.
- Files/modules: settings, Dockerfile, Compose, Nginx, `.env.example`, operations docs/tests.
- Deliverables:
  - [x] Production settings split, secure cookies, environment secret guard.
  - [x] Non-root Gunicorn image and one-shot migrate/static job.
  - [x] PostgreSQL readiness and Nginx static/proxy/request-ID/login limit.
  - [x] Add strict production environment validator and safe failure tests.
  - [x] Add bounded container logs, query-free structured edge logs, finite proxy timeouts, and process-level liveness checks.
  - [x] Split database init, migration-owner, and application roles; run a locked post-migration exact-grant finalizer before web starts.
  - [x] Require an exact external PostgreSQL volume name and isolate database traffic on the backend network.
  - [x] Make the web filesystem read-only with only `/tmp` writable and static files mounted read-only.
  - [x] Use a bounded 10,000-entry throttle cache under the portable platform temporary root for the approved single web container.
  - [x] Terminate TLS at Nginx, redirect fixed-host HTTP, and set an exact checked HSTS header on all HTTPS responses.
  - [x] Disable schema and interactive API docs in production.
  - [x] Keep production Compose free of local builds, require nonempty image inputs, enforce four version-plus-digest refs in the mandatory validator/release flow, and verify the Docker base digest/platform/interpreter at build time.
  - [x] Add a reversible edge write-stop that rejects write methods while reads and health stay available.
  - [ ] Prove image/stack boot when Docker exists.
- Migration/data impact: Startup applies reviewed migrations only through one-shot job.
- Security/authorization impact: Proxy trust, HTTPS readiness, least privilege, secret environment.
- Test plan: deploy checks, digest-input validation, Compose parse/pull/boot, write-stop, health/static/API smoke.
- Entry criteria: Runtime files mapped.
- Exit criteria: Repository config is complete. Production-like stack proof is isolated to Phase 12.
- Verification commands: deploy check, collectstatic, image-reference validator, Compose config/pull/up/ps/logs, HTTP/write-stop smoke.
- Rollback/recovery: Prior reviewed image digests and Compose/config; migration rollback follows the runbook.
- Risks/blockers: The direct TLS path is fixed in source. Docker/Nginx tools, live host, certificate files, renewal path, and runtime proof are absent.
- Evidence: `Dockerfile`, `compose.yml`, `nginx/default.conf`, `scripts/bootstrap-postgres.sh`, `docs/ops/TLS.md`, `docs/ops/DATABASE_ROLES.md`, strict production-environment/topology tests, and a clean safe-value deploy check. Docker/Nginx execution remains absent.

## Phase 9 - Database operations, backup, restore, observability

- Status: `DONE`
- Objective and scope: Safe PostgreSQL backup/retention/restore tools, structured logs, rotation, health, and recovery docs.
- Dependencies: Phase 8 topology; deployment owner chooses destination/retention before live use.
- Files/modules: scripts, Compose, Nginx, logging settings, operations runbooks.
- Deliverables:
  - [x] Add fail-closed backup script and explicit sentinel-protected backup-root contract.
  - [x] Add a separate read-only backup login and profile-only backup service with its own required external volume.
  - [x] Add optional age retention, disabled by default, limited to exact direct dump/checksum pairs; live daily/weekly policy remains blocked.
  - [x] Add host and standalone no-network container restore verifiers that share one boolean contract for nine core tables, three migration heads, twelve constraints, and two partial unique indexes.
  - [x] Configure bounded application/container log capture and safe proxy request-ID logs without query/referrer/browser-agent data.
  - [x] Write backup, restore-verification, and recovery runbook.
  - [x] Finish deployment, rollback, incident, release, database-role, TLS, dependency, and bootstrap runbooks.
- Migration/data impact: Restore runs only into explicit disposable target during tests.
- Security/authorization impact: Backup credentials stay in environment; dumps protected from web/runtime users.
- Test plan: script syntax/guards, fake-path safety tests, real disposable backup/restore when PostgreSQL exists.
- Entry criteria: Database topology and safety guards known.
- Exit criteria: Repo tools/docs complete. Real backup/restore proof and live policy are isolated external/decision gates.
- Verification commands: script guard tests, PostgreSQL harness, Compose job, restore smoke.
- Rollback/recovery: Scripts never mutate source DB; retention deletes only validated backup files in exact root.
- Risks/blockers: Live destination, schedule, retention, alert owner, recovery targets, and cutover authority are unresolved; native PostgreSQL client/runtime tools are absent.
- Evidence: `compose.yml`, `compose.restore-verify.yml`, `nginx/default.conf`, `common/request_logging.py`, guarded database scripts, `docs/ops/`, guard/parser tests, and the fresh 226-test fast suite. Source has four database roles, seven base service definitions, one isolated restore service, and two required external volumes. No real dump or restore ran.

## Phase 10 - Security, reliability, and performance verification

- Status: `DONE`
- Objective and scope: Close access, input, concurrency, query, dependency, and load risks using production-shaped tests.
- Dependencies: Phases 2-5 and 8-9 repo work.
- Files/modules: tests, selectors, services, serializers, settings, dependency manifest, security docs.
- Deliverables:
  - [x] Full approved role/object/filter matrix.
  - [x] CSRF/session/rate/malformed-input gates.
  - [x] Enforce a 64 KiB request-body cap, 32-container JSON-depth cap, stable `payload_too_large` HTTP 413, and safe malformed-input errors.
  - [x] PostgreSQL concurrency, constraint, upgrade, ACL/denial, dump, and rollback tests/harness exist; guarded native execution remains Phase 12.
  - [x] Query-count/N+1 review for fixed report queries and scoped APIs.
  - [x] Prove flat query growth for users, activity logs, customers, phones, leads, interactions, products, and sales list routes.
  - [x] Bounded GET-only health load harness and exact approval/evidence runbook with no credential, body, proxy, or redirect support.
  - [x] Focused harness argument, redirect, safe-output, and loopback tests.
  - [ ] Safe load smoke with an approved capacity target.
  - [x] Available dependency/source scans, exact hashed Python lock, Docker build base gate, and mandatory release-image validator.
- Migration/data impact: Index migrations only for measured query patterns.
- Security/authorization impact: Final P0/P1 closure.
- Test plan: critical path, attack matrix, concurrent workflows, query counts, smoke load.
- Entry criteria: Approved endpoints/reports complete.
- Exit criteria: No open repository P0/P1; evidence linked for all quality gates.
- Verification commands: targeted/full tests, PostgreSQL suite, dependency check/scanner, load script.
- Rollback/recovery: Revert isolated hardening/index change if measured regression appears.
- Risks/blockers: Capacity target, harness approval, target owners/abort rules, and live engine are needed for final tuning.
- Evidence: Fresh 226-test full suite passes with six PostgreSQL-only tests skipped; dependency/hash/image/source/schema and targeted access/fault/input/query-growth/load/scan-runbook tests pass. PostgreSQL execution, approved load, and external scanners remain explicit external/decision gates. Final independent P0/P1 audit remains open.

## Phase 11 - Documentation, UAT, and release candidate

- Status: `IN_PROGRESS`
- Objective and scope: Operator/user docs, safe UAT data, release checklist, known limits, and production-candidate evidence.
- Dependencies: Repository-controlled phases 0-10.
- Files/modules: docs, management commands/fixtures, checklist, release notes.
- Deliverables:
  - [x] Deployment, upgrade, rollback, migrate, admin, health, backup, restore, incident, TLS, and database-role runbooks.
  - [x] Synthetic Persian UAT seed with no real personal data and strict empty-target guards.
  - [x] Refresh OpenAPI validation and response assertions for sensitive-action `429` contracts.
  - [x] Release checklist, known limits, and clean source-level release evidence.
  - [x] Regenerate `docs/ops/SOURCE_MANIFEST.md` for the final settled 134-path current-worktree set and refresh release notes.
  - [ ] Record a fresh final read audit with no open repository-controlled P0/P1 after the current backend/operations follow-up.
  - [x] Mirror every `BIZ`, `SRC`, `EXT`, and human operations input in the blocker/readiness registers with exact close proof or command sets.
  - [ ] Record and review one exact commit/release artifact; complete repository checklist gates against that reference.
- Migration/data impact: UAT seed isolated from production; no automatic live load.
- Security/authorization impact: Operator commands preserve role/admin split and secret safety.
- Test plan: doc command dry runs, UAT workflow, schema, full release gates.
- Entry criteria: All repo code/config work complete.
- Exit criteria: Repository docs and local gates pass with no P0/P1; only explicit human/decision/external blockers remain. An immutable deploy/rollback artifact remains SRC-002/OPS-001 input and cannot be guessed or created automatically.
- Verification commands: release checklist commands and UAT smoke suite.
- Rollback/recovery: Release rollback runbook names image, migration, and backup paths.
- Risks/blockers: External environment proof remains phase 12.
- Evidence: Source/runbook/UAT work exists in `docs/ops/`, management-command tests, backend contract docs, this roadmap, `WORKLOG.md`, `PRODUCTION_READINESS_CHECKLIST.md`, and release notes. The exact 134-path manifest, fresh schema, 226-test suite, static/package/image/syntax/deploy checks pass. Final independent audit and immutable release identity remain pending.

## Phase 12 - Production environment proof

- Status: `BLOCKED`
- Objective and scope: Prove live-shaped PostgreSQL, Compose, Nginx, static, TLS, backup/restore, health, and rollback.
- Dependencies: Phases 0-11 complete; external runtime and deployment inputs.
- Files/modules: deployed image/config, runtime logs, evidence records only; no secret capture.
- Deliverables:
  - [ ] PostgreSQL zero/upgrade migration proof.
  - [ ] Compose digest pull/boot/health/static/API proof.
  - [ ] Nginx routing, rate, error, and request-ID proof.
  - [ ] Real disposable backup/restore proof.
  - [ ] Hostname/certificate/TLS proof.
- Migration/data impact: Only disposable or approved production migration with explicit recovery point.
- Security/authorization impact: Final transport, secret, network, and runtime trust proof.
- Test plan: production-like smoke/UAT, restore drill, TLS scanner, health/restart checks.
- Entry criteria: Repo candidate complete and external inputs approved.
- Exit criteria: All production readiness gates have direct evidence.
- Verification commands: Compose lifecycle, migration, HTTP/TLS smoke, backup/restore, rollback drill.
- Rollback/recovery: Approved backup plus image/config rollback; never test destructively on unverified live data.
- Risks/blockers: Current host lacks Docker, Nginx, and native PostgreSQL; hostname/certificate/server inputs absent.
- Evidence: `BLOCKERS.md`, future external proof records.
