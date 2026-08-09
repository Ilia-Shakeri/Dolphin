/goal Take the current Kariz CRM repository from its present state to a verified production-ready backend and a safely rebranded Persian-only active application. Do not stop after an internal task, slice, or phase and do not ask me to type “continue”. Build and maintain a phase-by-phase roadmap in the repository root, execute the next unblocked roadmap item automatically, verify every phase, and continue until the completion gates in this goal are satisfied or only genuine external/human blockers remain.

# Kariz CRM — Autonomous Completion and Production-Readiness Goal

You are the primary implementation, review, migration, cleanup, and release-readiness agent for **Kariz CRM / کاریز**. Work only inside the open Kariz CRM workspace. Treat this message as an explicit override of any older instruction that says to “stop after the requested slice”, “wait for continue”, or end work merely because a phase report was produced.

A milestone report is a checkpoint, not a stopping point. After recording a checkpoint, immediately select and execute the next unblocked roadmap task.

---

## 1. Authority and source handling

Use this precedence order:

1. `BACKEND_SPEC.md`, when present and internally consistent.
2. Explicit requirements in this goal.
3. Root and nested `AGENTS.md` / `AGENTS.override.md` files, except that this goal overrides any old stop-after-slice or wait-for-continue rule.
4. Approved architecture/domain documents under `docs/backend/`.
5. `codex_backend_context.txt` as selective frontend-contract and historical evidence only.
6. Existing implementation and tests, after checking that they follow the higher-priority sources.
7. Template/demo HTML and JavaScript only as UI evidence, never as authoritative business logic.

Do not silently invent business rules. Record unresolved business decisions in `ASSUMPTIONS.md` and `BLOCKERS.md`, isolate the affected behavior, and continue all independent work.

If `BACKEND_SPEC.md` or `codex_backend_context.txt` is present under a suffixed upload name such as `...(1).txt`, normalize or copy it to the canonical root filename without losing the original. If the files are genuinely absent, do not remain idle. Create a clearly marked provisional `BACKEND_SPEC.md` from the confirmed baseline in this goal plus current models, migrations, tests, and approved `docs/backend/` files. Mark every non-confirmed item as unresolved or provisional.

### Confirmed project baseline to use only when a stronger source does not override it

- Product name: `Kariz CRM` / `کاریز`.
- Stack: Django, Django REST Framework, PostgreSQL, Docker Compose, Nginx, Linux target, modular monolith.
- Internal browser/API preference: same-origin Django Session Authentication with CSRF.
- Fixed CRM role codes: `sales_agent`, `sales_manager`, `company_it`, `platform_admin`.
- CRM roles are separate from Django `is_staff`, `is_superuser`, groups, server access, and Docker/SSH access.
- Core entities: User, Customer, CustomerPhone, Lead, LeadAssignmentHistory, Interaction, Product, Sale, ActivityLog; predefined reports and XLSX export.
- Customer is an identity; Lead is a separate sales-cycle entry. One Customer can have multiple Leads.
- Sales Agents see only their own/assigned permitted data. Every list, retrieve, update, and custom action must enforce role-aware queryset/object scoping.
- Lead reassignment is a dedicated, audited service/action and creates assignment history.
- Products are read-only for Sales Agents and manageable by elevated roles.
- V1 uses a Sale entity for successful sales. Sale is not a legal/accounting Invoice.
- Full Invoice, postal/shipping-status, external SMS, ecommerce, inventory, tax, return/refund, and unrelated demo modules remain blocked unless a stronger approved source explicitly enables them.
- Reports are predefined and available in the CRM and as filtered XLSX exports.
- Do not expose secrets in source, logs, audit records, API responses, generated assets, or commits.

---

## 2. Continuous execution policy — do not wait for “continue”

Follow this loop until the goal is complete:

1. Read the current roadmap and worklog.
2. Select the highest-priority unblocked item whose dependencies are satisfied.
3. State a concise internal task boundary and files to inspect/change.
4. Make the smallest coherent implementation or cleanup batch.
5. Add or update tests in the same batch.
6. Run the narrowest relevant checks, then the required phase gate.
7. Inspect the diff and correct regressions.
8. Update roadmap status, evidence, codebase map, review ledger, assumptions, blockers, and worklog.
9. Immediately continue with the next unblocked item.

Never ask “Should I continue?”, “Do you want me to proceed?”, or equivalent for normal work inside the workspace.

Do not stop merely because:

- one phase completed;
- a status report was written;
- a non-blocking assumption exists;
- one roadmap item is blocked;
- Docker, native PostgreSQL, Nginx, TLS certificates, or Git metadata are initially unavailable;
- the next numerically ordered phase is blocked while later independent work is available.

When an item is blocked, mark it `BLOCKED`, document the exact missing input and impact, then choose another unblocked task.

### Pause only for a genuine hard blocker

Pause only when at least one of these is true and no safe independent work remains:

1. A secret, credential, production hostname, certificate, or external account must be supplied.
2. An irreversible external action is required, such as changing a real production system or migrating real production data.
3. A business decision changes data semantics and there is no safe way to isolate or defer it.
4. The active sandbox/permission boundary requires a human approval that cannot be avoided safely.
5. All code, documentation, test, cleanup, and local release tasks are complete and only external environment proof remains.

If the tool/session must end for a technical limit, persist a precise resume checkpoint in `WORKLOG.md`: current phase, completed evidence, exact next task, exact files, and exact commands. Do not present a normal phase boundary as if the project were finished.

---

## 3. First actions in this goal

Before adding new feature code:

1. Verify the repository root and active Django project.
2. Read `AGENTS.md`, canonical source documents, the existing roadmap/docs, current models, migrations, URLs, services, permissions, tests, production settings, Compose, and Nginx configuration using bounded reads.
3. Verify rather than blindly trust the previous reported state, including:
   - 61 passing tests;
   - request-ID middleware and response propagation;
   - trusted-proxy handling;
   - audit request/IP binding;
   - Sale product/price/quantity/total database constraints;
   - migrations through `sales.0005_sale_integrity_constraints`;
   - current production settings and Nginx configuration.
4. Create or update these durable root/project artifacts:

```text
PROJECT_ROADMAP.md
PRODUCTION_READINESS_CHECKLIST.md
CODEBASE_MAP.md
FILE_REVIEW_LEDGER.md
WORKLOG.md
BLOCKERS.md
ASSUMPTIONS.md
```

5. Update `AGENTS.md` non-destructively so that it contains the continuous-execution rule from this goal and no longer instructs Codex to stop after each slice. Preserve valid project-specific rules.
6. Establish a safe source-control baseline before deletion-heavy cleanup.

### Git baseline rule

If `.git/` is absent:

- inspect and improve `.gitignore` first;
- ensure `.env*` except `.env.example`, credentials, keys, databases, uploads, backups, logs, cache, generated build output, and local secrets are excluded;
- run a targeted secret/path scan;
- initialize Git locally;
- create a baseline commit only if Git user identity is already configured and the staged set contains no secrets or forbidden generated/binary data;
- never set an invented global Git identity and never push automatically;
- if a baseline commit cannot safely be created, mark deletion phases blocked, continue non-destructive work, and document the exact setup needed.

Never run `git reset --hard`, `git clean`, broad `rm -rf`, or mass deletion without an explicit reviewed manifest.

---

## 4. Root roadmap requirements

Create `PROJECT_ROADMAP.md` in the repository root before continuing broad implementation. It must be a living execution document, not a vague wishlist.

For every phase include:

- phase ID and title;
- status: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `DONE`, or `VERIFIED`;
- objective and scope;
- dependencies;
- files/modules involved;
- deliverables;
- migration/data impact;
- security and authorization impact;
- test plan;
- entry criteria;
- exit criteria;
- verification commands;
- rollback/recovery approach;
- known risks and blockers;
- evidence links or filenames;
- completion date/checkpoint when verified.

Use checkboxes for tasks, but do not treat checking a box as proof. Record command output or test evidence.

### Required roadmap phases

Adapt these phases to the real repository, merge already-completed work when evidence supports it, and do not redo correct work merely to match numbering.

#### Phase 0 — Repository safety and reproducible baseline

- canonical source documents;
- `.gitignore`, local Git baseline, secret scan;
- dependency and runtime inventory;
- baseline tests/checks/schema generation;
- no destructive cleanup before rollback is available.

#### Phase 1 — Architecture and codebase mastery

- application/module map;
- entity and relation documents kept separate;
- request/data-flow map;
- first-party file review ledger;
- identify duplicate, generated, demo, dead, and active code;
- identify language and branding surfaces.

#### Phase 2 — Core schema and migration integrity

- custom User/roles;
- Customer/CustomerPhone;
- Lead/assignment history;
- Interaction;
- Product;
- Sale snapshots and constraints;
- ActivityLog;
- clean migrations and PostgreSQL-compatible constraints/indexes;
- migration tests and no schema drift.

#### Phase 3 — Authentication, authorization, audit, and request security

- login/logout/me/session/CSRF;
- inactive-user behavior;
- role-aware querysets and object access;
- privilege-escalation tests;
- request IDs;
- proxy/IP trust boundaries;
- safe audit payloads;
- throttling and secure error responses.

#### Phase 4 — Services and versioned REST APIs

- service-layer transitions;
- serializers/request validation;
- filters/search/order/pagination;
- dedicated reassignment and sale correction/cancellation actions;
- consistent error contract;
- OpenAPI coverage;
- API and workflow tests.

#### Phase 5 — Predefined reports and XLSX

- implement all unambiguous metrics and filters;
- role-scoped report access;
- XLSX matching active filters;
- deterministic fixtures and zero-denominator handling;
- schema/OpenAPI/tests;
- isolate unresolved KPI semantics instead of blocking the repository.

#### Phase 6 — Persian-only active application cleanup

- inventory active locale files and selectors;
- remove unused languages safely;
- remove language-switch controls and behavior;
- force the approved Persian locale/RTL behavior in the active application;
- validate templates, JavaScript, static collection/build, and browser smoke paths.

#### Phase 7 — Kariz rebranding

- remove user-visible/vendor-origin branding from active application surfaces;
- centralize Kariz product identity;
- verify no forbidden visible vendor terms or external demo/vendor links remain in active runtime content;
- preserve runtime identifiers and legally required third-party notices.

#### Phase 8 — Production configuration and container stack

- production settings split;
- DEBUG off and strict host/origin configuration;
- secure cookies/CSRF/security headers;
- static/media strategy;
- Gunicorn or approved WSGI/ASGI server;
- Dockerfile/Compose health checks and restart policies;
- Nginx reverse proxy/static handling/request-ID headers;
- environment validation and least-privilege runtime.

#### Phase 9 — Database operations, backup, restore, and observability

- PostgreSQL persistent volume;
- migration startup/runbook;
- automated backup script/job;
- retention configuration;
- real restore test in a disposable database when runtime is available;
- structured/safe logs, rotation, request IDs, health/readiness checks;
- no secrets or sensitive payloads in logs.

#### Phase 10 — Security, reliability, and performance verification

- object-level access matrix tests;
- CSRF/session/security checks;
- rate-limit/throttle checks;
- malformed/large input checks;
- concurrency/integrity tests for critical workflows;
- query-count/N+1 review;
- indexes for proven query patterns;
- sensible load smoke test with documented assumptions;
- dependency/security checks available in the project environment.

#### Phase 11 — Documentation, operations, UAT, and release candidate

- complete OpenAPI;
- admin/operator commands;
- deployment, upgrade, rollback, backup, restore, and incident runbooks;
- seed/demo/UAT data without real personal data;
- release checklist and known limitations;
- clean production-like boot and smoke test;
- no open P0/P1 code/config/security blockers.

#### Phase 12 — Production environment proof

- live PostgreSQL migration proof;
- production-like Docker Compose boot;
- Nginx routing/static/health proof;
- TLS proof when hostname/certificate are available;
- backup and restore evidence;
- final release evidence.

External environment items may remain `BLOCKED_EXTERNAL`, but do not falsely label the project production-ready until the relevant proof exists. You may label it a “production candidate” with explicit remaining external gates.

---

## 5. Incremental file-by-file codebase mastery

The goal is to understand all **active first-party code**, not to consume every dependency, bundle, demo, or binary file.

Create and maintain `FILE_REVIEW_LEDGER.md`. Review the repository subsystem by subsystem and file by file in bounded batches, normally 10–25 related files at a time.

For every reviewed first-party file record:

- path;
- subsystem/owner;
- purpose;
- runtime entry point or caller;
- imports/dependencies;
- public interfaces/routes/templates;
- entities and relations touched;
- state changes and side effects;
- authorization/security concerns;
- tests covering it;
- language/branding references;
- active, duplicate, generated, demo, dead, or uncertain classification;
- follow-up action and roadmap link.

Also maintain `CODEBASE_MAP.md` with:

- Django apps and responsibilities;
- settings and deployment topology;
- URL/API map;
- request/auth/audit flow;
- data flow for Customer -> Lead -> Interaction -> Sale -> Report;
- template/JavaScript/static entry points;
- external dependencies and integrations;
- generated/vendor boundaries.

Do not repeatedly reread files already summarized unless a dependent change requires it. Use the ledger and map as persistent memory across turns.

### Never treat these as required file-by-file reading targets

Skip or inspect only by manifest/reference when necessary:

```text
.git/
.venv/
venv/
node_modules/
vendor/
dist/
build/
.next/
.cache/
__pycache__/
coverage/
htmlcov/
assets/plugins/
src/plugins/
assets/media/
src/media/
fonts/
*.min.js
*.bundle.js
*.chunk.js
*.map
*.png
*.jpg
*.jpeg
*.gif
*.webp
*.ico
*.woff
*.woff2
*.ttf
*.pdf
*.zip
*.db
*.sqlite
```

Do not read lockfiles as application logic. Do not read secrets.

Use targeted `git ls-files`, exact globs, `rg -n`, imports, URLs, template includes, static references, and bounded line ranges. Do not load the entire repository into one context.

---

## 6. Persian-only language cleanup

The active product UI is Persian-only unless `BACKEND_SPEC.md` explicitly says otherwise.

“Remove other languages” means removing unused locale packs, translated UI resources, language-selector UI, and language-selection behavior from the **active Kariz application**. It does not mean deleting programming-language source files, English API identifiers, Python/JavaScript keywords, database column names, developer-facing technical documentation, Django/framework package locales inside installed dependencies, or required third-party notices.

### Required safe procedure

1. Create `docs/codebase/LANGUAGE_CLEANUP.md`.
2. Inventory candidate locale/language resources and every reference to them. Look for exact active paths and patterns such as:
   - `locale/`, `locales/`, `lang/`, `languages/`, `i18n/`, `l10n/`;
   - locale JSON/JS files;
   - Moment, FullCalendar, DataTables, Select2, Flatpickr, Bootstrap, validation, and date-picker locale packs copied into the active tree;
   - Django `LANGUAGE_CODE`, `LANGUAGES`, `LocaleMiddleware`, translation URLs, cookies, query parameters, and template tags;
   - language dropdowns, flags, switch buttons, localStorage keys, event handlers, redirects, and profile language fields.
3. Identify the actual Persian locale(s) in use (`fa`, `fa-IR`, or project equivalent) and preserve required RTL/Persian assets.
4. Build a reference manifest before deleting anything. Do not delete based only on filename.
5. Remove the language switcher from shared templates/partials first, then remove its JavaScript handlers, storage/cookie/query behavior, profile language validation, and unused routes/settings.
6. Set one explicit default Persian locale using the project’s existing framework conventions.
7. Delete only proven-unused non-Persian locale files from the active source/static tree in small groups.
8. Do not edit minified bundles to remove embedded locale text. Prefer using a smaller source build or excluding the unused bundle from the active build. If no safe source build exists, document the limitation instead of corrupting a bundle.
9. Do not destructively clean the immutable original purchased/vendor archive. Clean the curated active Kariz repository and deployment artifact.
10. After every deletion group, run relevant template, JavaScript/build, static collection, and smoke checks. Restore the group if references break.
11. Record every removed file, removed selector, changed setting, verification command, and residual exception in `LANGUAGE_CLEANUP.md`.

### Language cleanup acceptance criteria

- no language switcher is rendered in active pages;
- no language-selection handler, route, query parameter, cookie, localStorage key, or profile field remains unless technically required and documented;
- active UI defaults to Persian and preserves RTL behavior;
- no active template/static import references a deleted locale file;
- template rendering and static/build checks pass;
- relevant browser smoke paths load without console/network errors;
- non-Persian locale resources are absent from the active deployment artifact, except documented dependency/runtime exceptions that cannot safely be removed.

---

## 7. Kariz-only branding cleanup

The user-visible and project-owned brand is:

```text
English: Kariz CRM
Persian: کاریز
Optional full Persian title: کاریز | سامانه مدیریت فروش و ارتباط با مشتری
```

Create `docs/codebase/BRANDING_CLEANUP.md` and perform a case-insensitive, reference-aware audit of active first-party text files for vendor/template-origin terms and links, including at least:

```text
Metronic
KeenThemes
Keen Themes
keenthemes.com
preview.keenthemes.com
devs.keenthemes.com
vendor/demo purchase or preview URLs discovered during the audit
```

Also inspect titles, meta tags, login text, footer, sidebar/header, logos and alt text, favicon references, email templates, OpenAPI title/description, Django admin headers, package/project metadata, Docker/Compose service names, README/runbooks, comments copied into first-party modules, demo upload URLs, and external vendor links.

### Rebranding rules

- Replace user-visible and first-party product branding with `Kariz CRM` / `کاریز`.
- Centralize brand strings/configuration where practical instead of duplicating them across pages.
- Remove external demo/purchase/support links from active application behavior.
- Remove fake upload or API endpoints pointing to vendor demo domains.
- Rename first-party files/classes/settings containing the old product/vendor brand only through a reference-aware refactor with tests.
- Do **not** blindly rename stable theme runtime symbols or selectors such as `KTMenu`, `KTDrawer`, `KTUtil`, `data-kt-*`, plugin API names, or vendor filenames when changing them could break behavior. These are implementation identifiers, not displayed branding.
- Do not edit minified/generated bundles solely to replace strings. Replace/exclude their source or deployment references safely.
- Do not delete or falsify third-party license/copyright notices that must be retained. Keep required notices in a private/internal `THIRD_PARTY_NOTICES.md` or dependency metadata while ensuring they are not shown as Kariz product branding in the user interface.
- The shipping active UI and project-owned runtime content must not display Metronic/KeenThemes branding or vendor purchase/preview URLs.

Add an automated repository/deployment policy check if practical. It should scan the active first-party/runtime paths for forbidden visible terms while allowing explicit documented exceptions such as `THIRD_PARTY_NOTICES.md`, immutable vendor archives outside deployment, and runtime `KT*` identifiers.

### Branding acceptance criteria

- active HTML titles, login pages, navigation, footer, admin site, OpenAPI, emails, docs intended for operators/users, and application metadata use Kariz branding;
- no active runtime link points to template purchase, preview, demo, or vendor upload endpoints;
- no user-visible Metronic/KeenThemes branding remains;
- runtime theme behavior still passes smoke checks;
- every residual vendor term is listed with an exact justified exception and is not user-visible branding.

---

## 8. Backend completion requirements

For each approved feature, ensure all applicable layers exist and agree:

- PostgreSQL schema and reviewed migrations;
- model/entity and database constraints/indexes;
- service/use-case layer for business transitions;
- selector/query layer where useful;
- serializer/request validation;
- API route/controller/viewset/action;
- authentication and role/object authorization;
- safe audit/event behavior;
- consistent error responses and request IDs;
- automated model/service/API/permission tests;
- OpenAPI schema and examples;
- operational documentation.

Do not allow serializers or ordinary endpoints to set server-controlled fields such as ownership, assignment, sold-by, CRM role, `is_staff`, or `is_superuser` outside dedicated authorized services.

Avoid ordinary hard deletion of historical business records. Use deactivation/cancellation according to the approved domain rules.

---

## 9. Phase 5 reports: proceed without inventing ambiguous KPI semantics

Do not leave the whole reports phase blocked merely because some KPI names are ambiguous.

When no stronger approved specification exists, implement and document only metrics whose field names state exact semantics, for example:

- `customers_created_count`: Customers whose `created_by` is the selected user and whose creation timestamp is inside the selected period;
- `sales_count`: confirmed Sales in the selected period and permitted scope;
- `sales_amount`: sum of confirmed `Sale.total_amount` in the selected period and permitted scope;
- `average_sale_amount`: `sales_amount / sales_count`, returning zero when `sales_count` is zero;
- clearly named interaction/call counts only when the qualifying outcome set is explicit in source code/docs.

Treat these as unresolved until explicitly approved:

- a generic “number of customers” metric that could mean created, assigned, handled, called, or sold customers;
- unique-customers-handled semantics;
- conversion-rate denominator;
- how historical reassignment affects retrospective ownership/denominators;
- final call-outcome groupings not defined by the backend source of truth.

For unresolved metrics:

- add a precise item to `BLOCKERS.md` and `ASSUMPTIONS.md`;
- do not publish a misleading generic field;
- keep report code extensible;
- continue with unambiguous metrics, filters, authorization, XLSX, OpenAPI, and tests.

XLSX output must reflect the same filters and authorization scope as the JSON report endpoint and open successfully in standard spreadsheet software.

---

## 10. Production-readiness gates

Do not claim “production ready” from static parsing alone. Mark each gate with evidence in `PRODUCTION_READINESS_CHECKLIST.md`.

### Application and schema

- `python manage.py check` passes under test and production-like settings;
- no migration drift;
- migrations apply from zero on PostgreSQL when available;
- upgrade path from the current migration state is tested;
- database constraints protect critical invariants;
- health/readiness checks verify database connectivity;
- OpenAPI schema generation/validation passes.

### Security

- DEBUG is false in production;
- secret key and credentials come only from environment/secret management;
- allowed hosts, trusted origins, secure cookies, CSRF, HSTS/security headers, proxy SSL handling, and request-IP trust are explicit and tested where feasible;
- no privilege escalation through role/admin fields;
- object-level isolation tests cover direct ID and filter/query attacks;
- inactive users lose access;
- authentication, authorization headers, passwords, tokens, keys, and sensitive payloads are never logged/audited;
- throttling/rate limits protect login and sensitive endpoints;
- dependency and source security checks available in the environment are run and documented.

### API and behavior

- versioned endpoints have validation, errors, pagination/filtering where appropriate, request IDs, authorization tests, and OpenAPI;
- service operations are transactional where required;
- reassignment/history/audit and Sale correction/cancellation are proven;
- filtered reports and XLSX are deterministic and role-scoped.

### Runtime and operations

- production Docker image builds reproducibly;
- Compose configuration parses and the stack boots in a production-like environment when Docker is available;
- application, PostgreSQL, and Nginx health checks work;
- static files and proxy routes work;
- restart policies and log rotation are configured;
- backup runs, retention is configurable, and at least one restore is tested in a disposable environment;
- deployment, migration, rollback, backup, restore, admin-user, health, and incident commands are documented;
- TLS configuration is validated when a real hostname/certificate path is supplied; otherwise this remains an explicit external blocker.

### Quality and release

- full test suite passes;
- targeted critical-path tests pass independently;
- no schema drift;
- no secrets or forbidden artifacts are tracked or shipped;
- no user-visible vendor branding or language switcher remains;
- Persian/RTL active pages pass smoke checks;
- no unresolved P0/P1 code/config/security defect remains;
- known business/external limitations are explicit;
- final diff/repository state is reviewable and release notes are complete.

---

## 11. Verification commands

Adapt commands to the actual project and available tools. Run the narrowest checks after each batch and the full gate at milestones.

Typical backend checks:

```bash
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py test --settings=config.test_settings -v 1
python manage.py spectacular --file /tmp/kariz-openapi.yaml --validate
```

Typical production-like checks:

```bash
python manage.py check --deploy --settings=config.production_settings
python manage.py collectstatic --noinput --settings=config.production_settings

docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs --no-color --tail=200
```

Typical source/release checks:

```bash
git diff --check
git status --short
git diff --stat
```

Also run any existing lint, formatting, type, JavaScript, template, browser, dependency, and policy checks already configured. Do not introduce a heavy new toolchain merely to claim a checkbox.

If a required runtime tool is unavailable, record the exact failed/unavailable command and continue all other work. Do not convert “tool unavailable” into “configuration verified”.

---

## 12. Change and deletion discipline

- Work in small coherent batches even though the overall goal is long-running.
- Never combine a broad backend refactor, locale deletion, and branding rewrite in one unreviewable patch.
- Before deleting files, create a candidate manifest with reference evidence and rollback point.
- Delete exact reviewed paths, not broad ambiguous glob trees.
- Add tests or policy checks that prevent regression where valuable.
- Preserve database migration history unless a stronger approved plan explicitly allows rebuilding pre-production migrations and proves there is no real data.
- Do not modify secrets or production credentials.
- Do not push, deploy to a real production host, rotate credentials, or destroy external data without explicit approval.

---

## 13. Worklog and progress behavior

Update `WORKLOG.md` after every meaningful batch with:

- timestamp/checkpoint;
- roadmap phase/task;
- files inspected;
- files changed/deleted;
- entities/relations/endpoints/migrations affected;
- tests/checks and results;
- assumptions/blockers;
- regressions found and fixed;
- exact next unblocked task.

You may send concise progress summaries during the run, but a progress summary is not a request for permission and must not terminate the goal.

At each phase gate, report:

- what became verified;
- evidence;
- remaining blockers;
- the next task you are starting immediately.

---

## 14. Final stopping condition

Stop the goal only when one of these final states is true:

### State A — Verified production ready

All applicable roadmap phases are `VERIFIED`; all production-readiness gates have evidence; PostgreSQL/Docker/Nginx/backup-restore/TLS requirements applicable to the target deployment are proven; no P0/P1 code/config/security blockers remain; the active application is Persian-only and Kariz-branded; tests and release checks pass.

### State B — Production candidate with only external blockers

All repository-controlled code, migrations, tests, docs, cleanup, security configuration, deployment configuration, and local verification are complete, and the only remaining items require external infrastructure or human-supplied inputs such as a production server, hostname, certificate, credential, capacity target, or final unresolved business decision. Every such item must be explicit in `BLOCKERS.md` and `PRODUCTION_READINESS_CHECKLIST.md`, with exact commands/evidence needed to close it.

Do not use “Done” for State B without the qualifier “production candidate; external verification pending”.

The final report must include:

- final roadmap status by phase;
- production-readiness gate table;
- files added/changed/deleted;
- migrations and data implications;
- endpoint/OpenAPI summary;
- test/check evidence;
- Persian-language cleanup evidence;
- Kariz-branding cleanup evidence;
- security findings and resolutions;
- deployment/backup/restore evidence;
- all remaining external/business blockers;
- exact release/deploy commands and rollback path.

Begin now by creating/updating the root roadmap and durable work artifacts, reconciling the current repository against the reported baseline, updating the continuous-execution rule in `AGENTS.md`, and then executing the highest-priority unblocked task. Do not wait for me to say “continue”.
