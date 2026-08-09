# Kariz CRM production roadmap

Last checkpoint: 2026-08-09. This file is the live execution source. A checked task needs evidence before phase status becomes `VERIFIED`.

Status values: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `VERIFIED`.

## Phase summary

| Phase | Title | Status | Next gate |
|---|---|---|---|
| 0 | Repository safety and reproducible baseline | IN_PROGRESS | Review, scan, and commit safe durable baseline |
| 1 | Architecture and codebase mastery | IN_PROGRESS | Finish active first-party ledger and runtime UI map |
| 2 | Core schema and migration integrity | IN_PROGRESS | Reconcile global phone identity and run PostgreSQL proof |
| 3 | Authentication, authorization, audit, request security | IN_PROGRESS | Reconcile Company IT matrix and rerun access tests |
| 4 | Services and versioned REST APIs | IN_PROGRESS | Stable error contract, audit read scope, schema proof |
| 5 | Predefined reports and XLSX | NOT_STARTED | Implement exact approved metrics and filters |
| 6 | Persian-only active application cleanup | NOT_STARTED | Build active-path language manifest |
| 7 | Kariz rebranding | NOT_STARTED | Build active-path brand manifest and policy check |
| 8 | Production configuration and container stack | IN_PROGRESS | Close logging/static/runtime config gaps |
| 9 | Database operations, backup, restore, observability | NOT_STARTED | Add safe backup/restore tools and runbook |
| 10 | Security, reliability, performance verification | NOT_STARTED | Complete access, query, input, concurrency, and load gates |
| 11 | Documentation, UAT, release candidate | NOT_STARTED | Complete runbooks, UAT seed, release evidence |
| 12 | Production environment proof | BLOCKED | Need native/runtime host, hostname, and certificate path |

## Phase 0 - Repository safety and reproducible baseline

- Status: `IN_PROGRESS`
- Objective and scope: Canonical sources, safe ignore rules, local rollback point, dependency/runtime inventory, and clean baseline gates.
- Dependencies: None.
- Files/modules: root source docs, `.gitignore`, `.dockerignore`, Git metadata, requirements, test settings.
- Deliverables:
  - [x] Confirm repository root and Django project.
  - [x] Find authoritative `BACKEND_SPEC.md`.
  - [x] Expand secret, database, backup, log, cache, and generated-output ignores.
  - [x] Run initial tracked high-confidence secret/path scan.
  - [ ] Review staged manifest and create safe baseline commit.
  - [ ] Record fresh full baseline checks after source reconciliation.
- Migration/data impact: None.
- Security/authorization impact: Prevent secret and generated artifact tracking; no runtime permission change.
- Test plan: Git path/secret scans, `git diff --check`, dependency check, Django check, migration drift, full tests, schema validation.
- Entry criteria: Current workspace accessible.
- Exit criteria: Canonical sources tracked, clean baseline commit exists, scans and baseline commands have evidence.
- Verification commands: `git status --short`; targeted `git ls-files`; `git grep`; Django check, migration drift, tests, schema validation.
- Rollback/recovery: Revert only reviewed documentation/ignore patch; never clean or reset broadly.
- Risks/blockers: Existing initial commit may contain large template artifacts; review by manifest, not blind deletion.
- Evidence: `docs/backend/DISCOVERY.md`, `WORKLOG.md`, initial commit `ef1c7f4`.

## Phase 1 - Architecture and codebase mastery

- Status: `IN_PROGRESS`
- Objective and scope: Durable map and bounded file-by-file review of active first-party backend and actual served UI.
- Dependencies: Phase 0 safe baseline before deletion work.
- Files/modules: Django apps, config, deployment files, active templates/static entry points, backend docs.
- Deliverables:
  - [x] Keep entity and relation documents separate.
  - [x] Create `CODEBASE_MAP.md` and `FILE_REVIEW_LEDGER.md`.
  - [ ] Review backend subsystem batches and link tests/routes.
  - [ ] Prove active frontend/template/static entry points.
  - [ ] Classify active, demo, generated, duplicate, dead, and uncertain paths.
- Migration/data impact: None.
- Security/authorization impact: Finds unguarded entry points and unsafe legacy surfaces.
- Test plan: Import/URL checks, template/static reference checks, active-path smoke tests.
- Entry criteria: Phase 0 baseline exists for any deletion.
- Exit criteria: All active first-party files have ledger rows; runtime/data/request flow map is complete.
- Verification commands: targeted `git ls-files`, `rg -n`, Django URL/schema checks, bounded template reference checks.
- Rollback/recovery: Documentation-only until exact deletion manifests exist.
- Risks/blockers: Static archive is large and excluded from backend image; do not confuse archive with active UI.
- Evidence: `CODEBASE_MAP.md`, `FILE_REVIEW_LEDGER.md`, backend catalogs.

## Phase 2 - Core schema and migration integrity

- Status: `IN_PROGRESS`
- Objective and scope: User, Customer/phone, Lead/history, Interaction, Product, Sale, and ActivityLog schema with confirmed constraints and clean migrations.
- Dependencies: Authoritative specification and migration inventory.
- Files/modules: `accounts/models.py`, `sales/models.py`, `auditlog/models.py`, migrations, model/workflow tests.
- Deliverables:
  - [x] Custom user and fixed role database guard.
  - [x] Lead assignment all-or-none guard.
  - [x] Sale state, money, snapshot-pair, and total arithmetic guards.
  - [x] Phone normalization and one active primary per Customer.
  - [ ] Replace per-Customer active phone uniqueness with confirmed global active identity rule.
  - [ ] Apply migrations from zero and upgrade path on isolated PostgreSQL.
- Migration/data impact: New phone uniqueness migration will preflight conflicting active rows before constraint change.
- Security/authorization impact: Prevent duplicate identities and malformed workflow ownership at database boundary.
- Test plan: SQLite fast guards plus isolated PostgreSQL migration/constraint suite.
- Entry criteria: Model rules reconciled with `BACKEND_SPEC.md`.
- Exit criteria: No drift; zero/upgrade migrations pass on PostgreSQL; all critical constraints proven.
- Verification commands: migration drift, full tests, `scripts/test-postgres.ps1` with native tools.
- Rollback/recovery: Additive migration with reversible constraint operations; preflight invalid rows before apply.
- Risks/blockers: Native PostgreSQL tools absent on current host; current data conflicts must never be auto-dropped.
- Evidence: migrations through `sales.0005_sale_integrity_constraints`, `docs/backend/POSTGRES_TESTING.md`.

## Phase 3 - Authentication, authorization, audit, and request security

- Status: `IN_PROGRESS`
- Objective and scope: Session/CSRF, inactive-user denial, exact role/object matrix, safe audit, request IDs, proxy trust, and throttling.
- Dependencies: Phases 1-2 maps and schema.
- Files/modules: account/sales permissions, selectors, services, views, middleware, audit service, Nginx, security tests.
- Deliverables:
  - [x] Login/logout/me and CSRF tests.
  - [x] Fail-closed unknown roles and scoped relations.
  - [x] Password validation and server-field rejection.
  - [x] Request ID and trusted-proxy audit binding.
  - [x] Login throttling at app and edge.
  - [ ] Reconcile Company IT operational rights with the current access matrix.
  - [ ] Complete role-by-route and filter/query attack matrix.
- Migration/data impact: None unless audit/index review finds proven need.
- Security/authorization impact: Direct access control and audit integrity.
- Test plan: Every role across list/retrieve/write/action, inactive users, CSRF, direct IDs, hidden relation IDs, spoofed forwarding headers.
- Entry criteria: Scoped selectors and services mapped.
- Exit criteria: Matrix tests prove every endpoint and action; no unresolved P0/P1 access defect.
- Verification commands: targeted account/sales/common tests, full suite, schema permission review.
- Rollback/recovery: Small selector/permission/service changes with focused tests.
- Risks/blockers: Sales Manager team-user scope remains unresolved; keep user writes blocked there.
- Evidence: request-context tests, account security tests, sales workflow/API tests.

## Phase 4 - Services and versioned REST APIs

- Status: `IN_PROGRESS`
- Objective and scope: All approved features have matching service, validation, scoped API, errors, audit, schema, and tests.
- Dependencies: Phases 2-3.
- Files/modules: services, serializers, views, URLs, exception handling, schema docs/tests.
- Deliverables:
  - [x] Versioned auth, users, customers, phones, leads/reassign, interactions, products, sales/cancel, health, schema/docs.
  - [x] Locked transitions and append-only interaction API.
  - [x] Search/order/pagination and documented status filters.
  - [ ] Add stable machine-readable error codes without leaking object existence.
  - [ ] Add approved read-only audit access by role/scope or record exact deferral.
  - [ ] Reconcile cancellation/correction contract and schema examples.
- Migration/data impact: None expected.
- Security/authorization impact: Object scopes and mutation gates remain server-enforced.
- Test plan: route-method matrix, validation shape/codes, schema actions/errors/examples, service rollback.
- Entry criteria: Current spec-to-route gap list complete.
- Exit criteria: Every approved backend capability has all layers and validated schema.
- Verification commands: full tests, schema validation, URL/method inspection, targeted workflow tests.
- Rollback/recovery: Revert one route/service batch; migrations not expected.
- Risks/blockers: Sale correction details and audit visibility granularity may require safe deferral.
- Evidence: `docs/backend/API_CONTRACT.md`, generated schema gate.

## Phase 5 - Predefined reports and XLSX

- Status: `NOT_STARTED`
- Objective and scope: Exact user-performance metrics, safe date/user/product filters, role scope, and matching XLSX.
- Dependencies: Phases 2-4; exact metrics in specification.
- Files/modules: `reports/`, routes, schema, requirements, tests, report docs.
- Deliverables:
  - [ ] `customers_created_count`, `sales_count`, `sales_amount`, `average_sale_amount`.
  - [ ] Safe date range and authorized user filter.
  - [ ] JSON endpoint and XLSX export with identical query result.
  - [ ] Zero-denominator behavior and deterministic fixtures.
  - [ ] OpenAPI and workbook-open tests.
- Migration/data impact: None expected; proven query indexes only if needed.
- Security/authorization impact: Agents own scope; Manager, Company IT, and Platform Admin company/user scope.
- Test plan: exact formulas, cancelled-sale exclusion, date boundaries, user scope, ID/filter attacks, JSON/XLSX parity.
- Entry criteria: Current authorization matrix reconciled.
- Exit criteria: Exact metrics and exports pass deterministic tests and schema validation.
- Verification commands: report test module, full suite, schema validation, workbook load.
- Rollback/recovery: Remove isolated report routes/code; no business data mutation.
- Risks/blockers: Generic customer count, conversion, outcome grouping, Jalali display, final columns remain blocked and excluded.
- Evidence: `BACKEND_SPEC.md` reporting contract, future report docs/tests.

## Phase 6 - Persian-only active application cleanup

- Status: `NOT_STARTED`
- Objective and scope: Prove active UI, preserve Persian/RTL, remove active language selection and unused locale resources safely.
- Dependencies: Phase 0 rollback baseline and Phase 1 active-path map.
- Files/modules: active templates, first-party scripts/static, settings, locale manifest.
- Deliverables:
  - [ ] Create `docs/codebase/LANGUAGE_CLEANUP.md` and reference manifest.
  - [ ] Set explicit Persian default and RTL behavior.
  - [ ] Remove active language switch UI and state behavior.
  - [ ] Delete only proven-unused active non-Persian locale files.
  - [ ] Template/static/browser smoke evidence.
- Migration/data impact: None unless a dormant profile language field is found; removal needs migration review.
- Security/authorization impact: Avoid unsafe query/cookie locale behavior; no role change.
- Test plan: template render, static collection/build, reference no-match, browser routes and console/network smoke.
- Entry criteria: Active UI entry point proven; Git rollback baseline present.
- Exit criteria: Active app is Persian/RTL only; no switch path or broken locale reference.
- Verification commands: targeted reference scans, template tests, static/build check, browser smoke.
- Rollback/recovery: Small exact deletion groups restored from Git if any reference breaks.
- Risks/blockers: Static archive may not be active; do not delete archive by guess.
- Evidence: future `docs/codebase/LANGUAGE_CLEANUP.md`.

## Phase 7 - Kariz rebranding

- Status: `NOT_STARTED`
- Objective and scope: Kariz identity on all active user/project surfaces without breaking stable theme symbols or notices.
- Dependencies: Phase 1 and active UI map; Phase 0 rollback baseline.
- Files/modules: active templates/static, admin config, schema metadata, docs, deployment metadata.
- Deliverables:
  - [ ] Create `docs/codebase/BRANDING_CLEANUP.md` and exact reference manifest.
  - [ ] Centralize active brand strings where practical.
  - [ ] Remove visible vendor/demo links and fake endpoints.
  - [ ] Add active-path brand policy test with documented exceptions.
  - [ ] Preserve required third-party notices outside user-visible brand.
- Migration/data impact: None.
- Security/authorization impact: Remove unsafe external demo/upload links.
- Test plan: active-path text/link scan, template/static/browser smoke, admin/schema title checks.
- Entry criteria: Active surfaces classified.
- Exit criteria: No user-visible vendor brand/demo links; residual terms justified and not visible.
- Verification commands: policy test, targeted scans, render/build/browser checks.
- Rollback/recovery: Reference-aware small edits; stable runtime symbols unchanged.
- Risks/blockers: Minified/vendor files are not edited for text replacement.
- Evidence: future `docs/codebase/BRANDING_CLEANUP.md`.

## Phase 8 - Production configuration and container stack

- Status: `IN_PROGRESS`
- Objective and scope: Secure settings, least-privilege image, migration job, static serving, health, proxy, restart, and environment validation.
- Dependencies: Phases 2-4 for application runtime.
- Files/modules: settings, Dockerfile, Compose, Nginx, `.env.example`, operations docs/tests.
- Deliverables:
  - [x] Production settings split, secure cookies, environment secret guard.
  - [x] Non-root Gunicorn image and one-shot migrate/static job.
  - [x] PostgreSQL readiness and Nginx static/proxy/request-ID/login limit.
  - [ ] Add explicit production environment validator and safe failure tests.
  - [ ] Add container log rotation and refine health/liveness use.
  - [ ] Prove image/stack boot when Docker exists.
- Migration/data impact: Startup applies reviewed migrations only through one-shot job.
- Security/authorization impact: Proxy trust, HTTPS readiness, least privilege, secret environment.
- Test plan: deploy checks, Compose parse, image build/boot, health/static/API smoke.
- Entry criteria: Runtime files mapped.
- Exit criteria: Repository config complete and production-like stack proof recorded.
- Verification commands: deploy check, collectstatic, Compose config/build/up/ps/logs, HTTP smoke.
- Rollback/recovery: Image tags and prior Compose/config; migration rollback follows runbook.
- Risks/blockers: Docker/Nginx tools and real TLS path absent on current host.
- Evidence: `Dockerfile`, `compose.yml`, `nginx/default.conf`, production setting tests.

## Phase 9 - Database operations, backup, restore, observability

- Status: `NOT_STARTED`
- Objective and scope: Safe PostgreSQL backup/retention/restore tools, structured logs, rotation, health, and recovery docs.
- Dependencies: Phase 8 topology; deployment owner chooses destination/retention before live use.
- Files/modules: scripts, Compose, Nginx, logging settings, operations runbooks.
- Deliverables:
  - [ ] Add fail-closed backup script and separate backup volume/path contract.
  - [ ] Add configurable daily/weekly retention without unsafe broad deletion.
  - [ ] Add disposable restore verification script.
  - [ ] Configure application/container/proxy log bounds and request IDs.
  - [ ] Write backup, restore, recovery, and incident runbooks.
- Migration/data impact: Restore runs only into explicit disposable target during tests.
- Security/authorization impact: Backup credentials stay in environment; dumps protected from web/runtime users.
- Test plan: script syntax/guards, fake-path safety tests, real disposable backup/restore when PostgreSQL exists.
- Entry criteria: Database topology and safety guards known.
- Exit criteria: Repo tools/docs complete; one real disposable restore proof recorded for verification.
- Verification commands: script guard tests, PostgreSQL harness, Compose job, restore smoke.
- Rollback/recovery: Scripts never mutate source DB; retention deletes only validated backup files in exact root.
- Risks/blockers: Destination and retention unresolved; native PostgreSQL absent.
- Evidence: future operations scripts and docs.

## Phase 10 - Security, reliability, and performance verification

- Status: `NOT_STARTED`
- Objective and scope: Close access, input, concurrency, query, dependency, and load risks using production-shaped tests.
- Dependencies: Phases 2-5 and 8-9 repo work.
- Files/modules: tests, selectors, services, serializers, settings, dependency manifest, security docs.
- Deliverables:
  - [ ] Full role/object/filter matrix.
  - [ ] CSRF/session/rate/malformed/large-input gates.
  - [ ] PostgreSQL concurrency and constraint tests.
  - [ ] Query-count/N+1 review and proven indexes.
  - [ ] Safe load smoke with stated capacity assumption.
  - [ ] Available dependency/source scans.
- Migration/data impact: Index migrations only for measured query patterns.
- Security/authorization impact: Final P0/P1 closure.
- Test plan: critical path, attack matrix, concurrent workflows, query counts, smoke load.
- Entry criteria: Approved endpoints/reports complete.
- Exit criteria: No open repository P0/P1; evidence linked for all quality gates.
- Verification commands: targeted/full tests, PostgreSQL suite, dependency check/scanner, load script.
- Rollback/recovery: Revert isolated hardening/index change if measured regression appears.
- Risks/blockers: Capacity target and live engine needed for final tuning.
- Evidence: future security/reliability report and test outputs.

## Phase 11 - Documentation, UAT, and release candidate

- Status: `NOT_STARTED`
- Objective and scope: Operator/user docs, safe UAT data, release checklist, known limits, and production-candidate evidence.
- Dependencies: Repository-controlled phases 0-10.
- Files/modules: docs, management commands/fixtures, checklist, release notes.
- Deliverables:
  - [ ] Deployment, upgrade, rollback, migrate, admin, health, backup, restore, incident runbooks.
  - [ ] Synthetic Persian UAT seed with no real personal data.
  - [ ] Complete OpenAPI and endpoint summary.
  - [ ] Release notes, limitations, and clean production-like smoke evidence.
  - [ ] No open repository-controlled P0/P1.
- Migration/data impact: UAT seed isolated from production; no automatic live load.
- Security/authorization impact: Operator commands preserve role/admin split and secret safety.
- Test plan: doc command dry runs, UAT workflow, schema, full release gates.
- Entry criteria: All repo code/config work complete.
- Exit criteria: Production candidate package is reviewable; only explicit external blockers remain.
- Verification commands: release checklist commands and UAT smoke suite.
- Rollback/recovery: Release rollback runbook names image, migration, and backup paths.
- Risks/blockers: External environment proof remains phase 12.
- Evidence: future release notes and completed checklist.

## Phase 12 - Production environment proof

- Status: `BLOCKED`
- Objective and scope: Prove live-shaped PostgreSQL, Compose, Nginx, static, TLS, backup/restore, health, and rollback.
- Dependencies: Phases 0-11 complete; external runtime and deployment inputs.
- Files/modules: deployed image/config, runtime logs, evidence records only; no secret capture.
- Deliverables:
  - [ ] PostgreSQL zero/upgrade migration proof.
  - [ ] Compose build/boot/health/static/API proof.
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
