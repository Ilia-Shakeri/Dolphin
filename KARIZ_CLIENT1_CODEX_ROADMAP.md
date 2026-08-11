# Kariz CRM — Client 1 Step-by-Step Roadmap

## How to use this document

Run only one phase at a time. Do not run the next phase until its gate is green and `KARIZ_PROJECT_HANDOFF.md` contains the exact resume point.

C1-0 is complete. C1-1 source reconciliation is complete, but decision closure is still `BLOCKED_DECISION`. The direct Client-1 User Management instruction dated 2026-08-11 confirms the existing four fixed CRM roles and current backend access matrix. C1-2 still must not start until seat/capacity, Team, and after-sales workstream decisions are approved.

This roadmap gives phase steps. `KARIZ_PROJECT_HANDOFF.md` remains the only live status and evidence source.

## Phase map

| Phase | Purpose | May change production behavior? | Gate |
|---|---|---:|---|
| C1-0 | Baseline verification and provisional intake | No | Current repository truth recorded |
| C1-1 | Reconcile the customer's final list and approve scope | No | Every requirement is approved or explicitly blocked |
| C1-2 | Sales/after-sales operator separation | Yes | Identity and authorization matrix pass |
| C1-3 | Operational sales document, geography, and postal workflow | Yes | Document/postal reports pass |
| C1-4 | Contact-status reporting and detailed user performance | Yes | Definitions, scope, drill-down, and formulas pass |
| C1-5 | After-sales panel | Yes | Case workflow and workstream isolation pass |
| C1-6 | Inbound SMS foundation and report | Yes / external adapter may remain blocked | Idempotency, timezone, and provider security pass |
| C1-7 | Unified dashboard and active-UI hardening | Yes | All seven client capabilities are integrated in repository |
| C1-8 | PostgreSQL/Docker/Nginx/backup runtime proof | Runtime only | Production-like staging evidence passes |
| C1-9 | Target-site deployment, UAT, and controlled cutover | External/production | Client sign-off and rollback evidence exist |

## Controlled implementation baseline - 2026-08-11

This is the phase-planning mirror of `KARIZ_PROJECT_HANDOFF.md` section 23. It records code truth without changing behavior, style, or architecture.

### Current module and delivery truth

| Area | Existing now | Client-1 gap |
|---|---|---|
| Accounts | Four fixed clean CRM roles; session login/logout/me; profile; controlled user lifecycle and role change. | Team/workstream, session inventory/revoke, avatar, notices, export, seat/capacity acceptance. |
| Customer/phone | Scoped Customer CRUD/deactivate; optional postal code and plain-text category; read-only primary-phone projection; many normalized phones; duplicate and primary guards; paged scoped Lead/Interaction/Sale profile relations. | Governed category taxonomy, country-specific postal validation, document link, export/bulk/merge. |
| Lead/contact | Scoped Lead CRUD; manual reassignment/history; append-only manual Interaction. | Final statuses, Team/auto-assign, priority/archive/conversion/Pipeline, contact status, timeline/calendar/task/reminder, specialist report, telephony. |
| Product/Sale | Elevated Product manage, agent read; operational Sale snapshot/create/cancel. | Category/form expansion, Inventory/pricing/profit, Order/quotation/Invoice, postal, Payment/finance/PDF. |
| Reports/audit | Four exact performance metrics, JSON/XLSX parity, scoped read-only audit. | Drill-down, dashboard, SMS/contact/geography/postal/domain/P&L/receivable reports, dynamic builder. |
| Active UI | 19 maintained Persian RTL templates connected to real APIs for current core. | No maintained after-sales, document/postal, SMS, expanded report, file, import, automation, or integration pages. |
| Runtime | PostgreSQL/Compose/Nginx/backup-ready repository artifacts and local checks exist. | Native target stack, TLS/browser, real backup/restore, load/scan, UAT/cutover proof. |

### Existing API and template boundary

- Existing API families: auth; users plus change-role; customers plus deactivate and paged related Lead/Interaction/Sale reads; customer phones plus deactivate; leads plus assignees, assignment-history, and reassign; append-only interactions; products plus deactivate; sales plus cancel; user-performance JSON/XLSX; read-only activity logs; live/ready health.
- Existing templates: shell/error/login/profile; user list/detail; Customer list/detail profile with fields, phone work, and scoped related records; Lead list/detail; Interaction list/detail; Product list/detail; Sale list/detail; performance report; ActivityLog list/detail.
- Existing role boundary: Sales Agent gets own/assigned operational scope; Sales Manager gets company operational scope but no user admin or audit; Company IT manages non-platform CRM users and scoped audit; Platform Admin has full CRM user/audit scope. Product writes, reassignment, Customer deactivate, and Sale cancel are elevated-only.
- Common guard: active clean CRM identity, backend queryset/object scope, direct-ID masking, server-owned fields, safe audit, sensitive throttles, and no normal hard delete of business history.

### Original Client-1 requirement state

| Requirement | State | Current gap |
|---|---|---|
| C1-REQ-001 sales panel/no seat cap | `BLOCKED_DECISION`; partial core exists | Seat meaning, role/workstream/team, panel acceptance, capacity/load/UAT. |
| C1-REQ-002 after-sales panel/no seat cap | `BLOCKED_DECISION`; absent | Identity, case schema/workflow, scope, document link, capacity/UAT. |
| C1-REQ-003 detailed performance/drill-down | `BLOCKED_DECISION`; summary only | Metrics, formulas, drill-down, scope, samples, time/export parity. |
| C1-REQ-004 inbound SMS day/hour | `BLOCKED_DECISION` plus live `BLOCKED_EXTERNAL`; absent | Provider/security/idempotency/storage/time/report contract. |
| C1-REQ-005 document count by city/province | `BLOCKED_DECISION`; absent | Counted document, geography snapshot, date/formula/scope. |
| C1-REQ-006 incoming number by contact status | `BLOCKED_DECISION`; absent | Counted unit, dedupe, status derivation, time/scope. |
| C1-REQ-007 document count by postal status | `BLOCKED_DECISION`; absent | Document, postal state/history/actor/date/report contract. |

### Current gate and implementation order

1. Close C1-DEC-GOV-001, SEAT-001, TEAM-001, and AFTER-001. The fixed four-role User Management matrix is confirmed; the future Team/after-sales workstream matrix and capacity rule remain open.
2. Run C1-2 identity/operator separation.
3. Approve and run C1-3 document/geography/postal base.
4. Approve and run C1-4 contact-status and detailed performance.
5. Approve and run C1-5 after-sales.
6. Approve and run C1-6 SMS core/report; live adapter needs official provider docs.
7. Build approved normal-priority Lead/Product/collaboration/report/platform additions.
8. Build `FINAL_WAVE_LOW` Inventory/finance/files/search-import/PDF/dynamic-report/checked integrations.
9. Run C1-7 unified active UI.
10. Run C1-8 runtime proof, then C1-9 target UAT/cutover.

Assessment changed only this roadmap and `KARIZ_PROJECT_HANDOFF.md`. No migration, endpoint, UI route/template/style, permission, or architecture changed.

### Sidebar placeholder slice - 2026-08-11

- Status: `DONE`; navigation hierarchy only.
- Changed template: `common/templates/common/base.html`.
- Theme, colors, typography, RTL, layout, CSS architecture, JavaScript, UI routes, APIs, authorization, models, and migrations: unchanged.
- Expandable groups: Store, Call Center, Reports, and role-gated Administration.
- Real links retained: Profile, Products, Customers, Leads, Interactions, Sales, user-performance report, ActivityLog, and user management under current role guards.
- Future non-link placeholders: Dashboard, Inventory, Accounting, Categories, Invoices, Finance, Daily Tasks, Delivery, Targets, and Documents.
- Future group shells with live children: Store, Call Center, and Reports. The group shell itself has no backend landing route.
- Safety: future leaves use `aria-disabled`; no `href="#"`, fake success, backend call, or dead route was added.
- Tests: focused auth/sales/commercial shell suite PASS with 37 tests; headless Chrome shell PASS with 2 tests; Django check, migration drift, HTML branding for 220 files, and diff whitespace gate PASS.
- Remaining backend work: dashboard metrics; inventory/warehouse; accounting/document truth; Product category; provider-backed call-center work; Invoice/order model; detailed/domain reports; finance/ledger; task/calendar/reminders; postal delivery workflow; target formulas; secure file storage. Each remains blocked by its matching C1 decision and phase.
- Next phase remains C1-1 decision closure for seat/capacity, Team, and after-sales workstream rules, then C1-2 preflight. Placeholder creation does not clear a feature gate.

### Client-1 User Management completion - 2026-08-11

- Status: `DONE` for the requested User Management boundary.
- Confirmed roles: `sales_agent`, `sales_manager`, `company_it`, and `platform_admin`. This direct instruction supersedes the earlier three-label ambiguity for current User Management.
- Existing live behavior verified: login, logout, current-profile read/edit, user list/detail, user create/edit/deactivate, dedicated role change, backend role scope, clean CRM identity isolation, last active Platform Admin guard, safe audit, and no user DELETE route.
- Backend access: Sales Agent and Sales Manager cannot enter user administration; Company IT manages non-platform CRM users and cannot grant or target Platform Admin; Platform Admin manages all clean CRM users. Sales Manager stays denied until a Team contract exists.
- Added acceptance proof in `accounts/tests/test_accounts.py`: sales-role permission isolation, immediate inactive-session/login rejection, safe deactivation audit, Company IT escalation rejection through general update and role action, and HTTP 405 with preserved row for DELETE.
- Production code, templates, client script, style, architecture, models, migrations, endpoints, and routes: unchanged because the implementation already met the approved contract.
- Verification: focused account class 28/28 PASS; accounts plus auth shell/browser 61/61 PASS; full suite 279 run with 273 pass and 6 skip; system check, migration drift, schema validation, static dry-run, JavaScript syntax, branding, and whitespace gates PASS.
- Remaining account additions not approved by this slice: Team-aware Sales Manager administration, sales/after-sales workstream, session inventory/revoke, avatar, notifications, and user export.
- Next phase: close seat/capacity, Team, and after-sales workstream decisions, then rerun C1-2 preflight. Do not alter the four fixed role codes.

### Client-1 Customer Management completion - 2026-08-11

- Status: `DONE` for the requested Customer Management boundary.
- Existing `full_name` remains the API name field so old clients do not break. Added optional `postal_code` with 32-character bound and optional plain-text `category` with 100-character bound. Old payloads remain valid and receive blank values.
- No category entity, hierarchy, fixed list, or lifecycle was invented. No postal country/format rule was invented. Those values stay bounded text until a later approved contract.
- Customer responses now add read-only `primary_phone` with ID, raw number, normalized number, and label. Existing nested create phone and `customer-phones/` API remain unchanged.
- Existing phone label, Iranian normalization, database-backed global active duplicate prevention, one active primary phone per Customer, scoped update, and deactivate behavior remain authoritative.
- Added paginated read-only profile routes: `GET customers/{id}/leads/`, `GET customers/{id}/interactions/`, and `GET customers/{id}/sales/`. Customer direct IDs are scoped first; each relation then reuses its existing backend selector.
- Maintained Persian RTL list/detail pages now create/edit postal code and category, show primary phone in the list, and show paged related Leads, Interactions, and Sales. Existing classes and CSS architecture are unchanged.
- Delete control remains absent. Existing `POST customers/{id}/deactivate/` stays the only Customer removal-like UI action and preserves history.
- Migration: `sales.0011_customer_profile_fields`; additive blank-safe columns only, no data rewrite.
- Tests: focused backend/UI/schema/query suite 72/72 PASS; headless browser 2/2 PASS; full suite 282 run, 276 pass, 6 skip; system check, migration drift, UTF-8 schema validation, and no-warning gate PASS.
- Remaining Customer work outside this slice: governed category taxonomy if wanted, approved postal normalization, document relation, export, bounded bulk operations, and merge rules.
- Next recommended phase remains closure of seat/capacity, Team, and after-sales workstream decisions before broad C1-2. Customer document/geography/postal-report work still needs its separate C1-3 contract.

---

# C1-0 — Baseline verification and provisional intake

**Run this today.**

```text
Work directly in the curated Kariz CRM repository.

Read and obey first:
- AGENTS.md
- BACKEND_SPEC.md
- KARIZ_PROJECT_HANDOFF.md
- docs/backend/API_CONTRACT.md
- docs/backend/ENTITY_CATALOG.md
- docs/backend/RELATIONSHIPS.md
- docs/backend/ERD.mmd if it exists
- relevant docs/ops runbooks only when needed for verification

Do not inspect the parent Metronic/vendor archive. Do not recursively index vendor, node_modules, build, media, font, minified, generated, cache, or binary trees.

Do not create another roadmap, status, worklog, blocker, readiness, or progress Markdown file. KARIZ_PROJECT_HANDOFF.md is the single live status document.

Do not commit automatically. Do not run destructive Git commands. Do not delete or modify the user's untracked review bundle or code-dumper files.

Goal:
Verify the current repository baseline and record the first client's INITIAL requirements as provisional intake only. The final detailed customer list is expected later, so do not approve business semantics and do not implement functional code in this phase.

Record these provisional Client-1 requirement IDs in a clearly named section of KARIZ_PROJECT_HANDOFF.md:

- C1-REQ-001: Sales panel with no software-enforced account/seat limit.
- C1-REQ-002: After-sales panel with no software-enforced account/seat limit.
- C1-REQ-003: Management panel showing detailed user performance and drill-down.
- C1-REQ-004: Inbound SMS count report grouped by day and hour.
- C1-REQ-005: Invoice/sales-document count report grouped by city and province.
- C1-REQ-006: Incoming-number report grouped by contact status.
- C1-REQ-007: Registered invoice/sales-document report grouped by postal status.

For every requirement above:
- mark it PROVISIONAL and BLOCKED_DECISION;
- state that the wording comes from the initial client list and is not yet an implementation contract;
- map it to current repository capabilities and the exact missing domain decisions;
- do not invent models, statuses, metrics, filters, roles, workflows, providers, or legal/accounting meaning.

Create a concise decision checklist in KARIZ_PROJECT_HANDOFF.md for the final customer meeting/list. It must cover at least:

1. Meaning of “unlimited users”: no application seat cap versus expected concurrent-user capacity.
2. Exact sales and after-sales user types, manager boundaries, cross-panel access, and user lifecycle.
3. Meaning of “invoice”: existing Sale, internal order/document, or legal/accounting invoice; line items, numbering, cancellation/correction, amount, and source of truth.
4. Province/city source, required/optional values, historical snapshot behavior, and date basis for reporting.
5. Exact postal statuses, who may change them, manual versus provider integration, tracking code, history, return, and cancellation behavior.
6. Meaning of “incoming number”: Lead, unique phone, call, SMS sender, imported batch row, or another source; deduplication and date basis.
7. Exact contact statuses, current-status derivation, qualifying interaction, no-contact behavior, and whether latest interaction wins.
8. Exact user-performance metrics, denominators, drill-down rows, filters, export columns, and visibility by role.
9. SMS provider, webhook/polling method, authentication/signature, idempotency key, retained fields, message-body retention, timezone, and Jalali/Gregorian presentation.
10. Existing data/import needs, sample reports/documents, UAT users, target server, expected peak concurrency, backup owner, and acceptance sign-off.

Reconcile the live handoff evidence with actual commands. Trust executed commands over stale counts. Do not change BACKEND_SPEC.md business contracts in this provisional phase unless correcting an objectively stale repository fact.

Run:
- git rev-parse HEAD
- git status --short
- python manage.py check --settings=config.test_settings
- python manage.py makemigrations --check --dry-run --settings=config.test_settings
- python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
- python manage.py test --settings=config.test_settings -v 1
- python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
- node --check common/static/common/kariz-app.js
- python scripts/check_html_branding.py
- git diff --check
- git diff --stat

Mandatory handoff protocol:
- Update KARIZ_PROJECT_HANDOFF.md after each coherent subtask, not only at the end.
- Record phase, task, files inspected, files changed, migrations, endpoints/UI routes, authorization impact, exact commands/results, assumptions, decisions, blockers, current commit, git status, and exact next action.
- If any check fails, the session is interrupted, or a blocker is found, update the handoff before stopping with the exact resume command.
- Do not write secrets, credentials, customer personal data, raw private payloads, or tokens into the handoff.

This phase must have:
- no functional feature implementation;
- no model or migration changes;
- no new API/UI route;
- no approval of provisional statuses or entities.

Stop after C1-0.

Output exactly one concise line:
DONE or FAILED | baseline tests | changed files | blockers | next phase C1-1
```

---

# C1-1 — Final requirement reconciliation and approved delivery contract

**Run after receiving the customer's final detailed list and placing it in the repository workspace or otherwise making it available for repository assessment.**

```text
Work directly in the curated Kariz CRM repository.

Read and obey first:
- AGENTS.md
- BACKEND_SPEC.md
- KARIZ_PROJECT_HANDOFF.md
- the customer's final requirement source supplied for Client 1
- docs/backend/API_CONTRACT.md
- docs/backend/ENTITY_CATALOG.md
- docs/backend/RELATIONSHIPS.md
- docs/backend/ERD.mmd if it exists
- docs/ops/UAT.md

Do not inspect the parent Metronic/vendor archive. Do not create another roadmap/status/worklog file. Do not commit automatically. Do not run destructive Git commands.

Goal:
Convert the customer's final requirement source into an approved, testable Client-1 delivery contract before any schema or feature implementation.

First compare:
- the seven provisional C1 requirements in KARIZ_PROJECT_HANDOFF.md;
- the customer's final detailed list;
- current BACKEND_SPEC.md;
- current implemented repository behavior.

For each Client-1 requirement, create or update one stable capability ID in KARIZ_PROJECT_HANDOFF.md with these fields:
- source wording;
- approved normalized wording;
- business owner;
- target users/roles/workstreams;
- trigger/input;
- stored data and source of truth;
- allowed state transitions;
- filters/date basis/timezone;
- report formula and grouping semantics;
- UI route and API shape at a contract level;
- authorization/object scope;
- audit requirement;
- migration/data-import impact;
- acceptance examples, including empty and error cases;
- dependency IDs;
- status: APPROVED, BLOCKED_DECISION, BLOCKED_EXTERNAL, or OUT_OF_SCOPE.

Resolve or explicitly block the following high-risk ambiguities. Never guess:

A. User capacity
- Confirm that “unlimited users” means no software-enforced seat cap.
- Record that concurrent capacity is bounded by the approved server/load target and must not be marketed as infinite.

B. Sales versus after-sales identity
- Confirm whether the existing four CRM roles remain unchanged.
- Confirm whether an additive workstream/profile is approved, or whether another explicit identity design is required.
- Define manager visibility and whether Company IT/Platform Admin operate across both areas.

C. Invoice/sales document
- Decide whether the requirement maps to existing Sale, a new internal SalesOrder/document, or a legal/accounting invoice.
- If legal/accounting semantics, numbering, tax, correction, payment, or fiscal requirements are not fully defined, mark that domain blocked and select only an explicitly approved internal operational document if the customer accepts it.
- Define line items, one-to-one/one-to-many relationship with Sale, snapshots, cancellation, and report date.

D. Province/city and postal workflow
- Define the source and historical snapshot rule.
- Define exact postal statuses and transitions.
- Define whether current status only or append-only status history is required.
- Define tracking code and manual/provider ownership.

E. Incoming number/contact status
- Define the counted unit exactly.
- Define deduplication and time period.
- Define whether current status is derived from the latest Interaction and the deterministic tie-break rule.
- Define the no-interaction state.

F. Detailed user performance
- Define every metric and denominator.
- Define drill-down records and permitted roles.
- Define JSON/XLSX/UI parity and date/time behavior.

G. Inbound SMS
- Identify provider and official documentation.
- Define signature/authentication, idempotency, replay handling, retained fields, body retention, and report timezone/calendar.
- If provider documentation is unavailable, mark only the live adapter BLOCKED_EXTERNAL; do not invent a public webhook.

Update BACKEND_SPEC.md only with confirmed decisions. Keep unresolved items explicitly UNRESOLVED/BLOCKED. Update technical contracts only where a confirmed decision requires it. Do not implement functional code, models, migrations, endpoints, or UI in this phase.

Produce an implementation dependency order in KARIZ_PROJECT_HANDOFF.md. The expected default order is:
1. identity/operator separation;
2. operational sales document and postal/geography foundation;
3. contact-status and performance reporting;
4. after-sales workflow;
5. inbound SMS core/adapter;
6. unified dashboard/UI hardening;
7. runtime proof;
8. target deployment/UAT.
Change this order only when the confirmed requirement dependencies justify it, and record why.

Run documentation and baseline checks:
- git diff --check
- python manage.py check --settings=config.test_settings
- python manage.py makemigrations --check --dry-run --settings=config.test_settings
- python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
- python manage.py test --settings=config.test_settings -v 1
- python scripts/check_html_branding.py

Mandatory handoff protocol:
- Update KARIZ_PROJECT_HANDOFF.md after each requirement group is reconciled.
- Record files inspected/changed, confirmed decisions, unresolved questions, no-code status, exact command results, current commit/status, and the exact first implementation task.
- If any source is ambiguous, mark BLOCKED_DECISION and continue all independent reconciliation work.
- Before stopping, ensure there is one exact resume point and no provisional item is silently presented as approved.

Stop after C1-1.

Output exactly:
DONE or BLOCKED_DECISION or FAILED | approved capabilities | unresolved decisions | changed files | next phase
```

---

# C1-2 — Sales/after-sales operator separation

```text
Work directly in the curated Kariz CRM repository.

Read and obey first:
- AGENTS.md
- BACKEND_SPEC.md
- KARIZ_PROJECT_HANDOFF.md
- approved Client-1 capability/identity decisions from C1-1
- accounts and sales models/services/selectors/permissions/serializers/views/tests
- active first-party user-management and navigation files

Do not inspect or modify unrelated vendor/minified files. Do not create another status/roadmap file. Do not commit automatically. Do not run destructive Git commands.

Goal:
Implement the exact approved separation between sales operators and after-sales operators, with backend enforcement and no software seat cap.

Fail closed:
- If C1-1 did not approve the identity design, do not invent one. Update KARIZ_PROJECT_HANDOFF.md with BLOCKED_DECISION and stop.
- Preserve the confirmed four fixed CRM roles. This role-count decision is closed for User Management.
- The preferred additive design is a bounded operator workstream/profile such as sales and after_sales, but implement it only if it is explicitly APPROVED in the handoff/spec.
- Do not introduce a dynamic permission builder, Django-group-based CRM authorization, JWT, or a hidden support account.

Implement the approved design end to end:
- additive model field(s) and database constraints;
- safe migration and default/backfill behavior for existing users;
- reusable access helpers rather than scattered raw conditionals;
- serializers/services for authorized user administration;
- own-profile protection;
- audit of identity/workstream changes without private payloads;
- queryset, object, service, and custom-action authorization;
- role/workstream-correct first-party navigation and pages;
- no hard-coded maximum account count or licensing gate.

Required behavior unless the approved matrix says otherwise:
- sales operators keep only approved sales operations;
- after-sales operators can sign in and edit their own permitted profile but cannot gain sales Lead/Interaction/Product/Sale/report access merely because they share a base role;
- elevated roles retain only the approved cross-area visibility;
- inactive users lose access immediately;
- server-managed staff/superuser/group/direct-permission identities remain isolated from CRM identities;
- frontend hiding is not authorization.

Do not create the after-sales case model in this phase. If the after-sales panel does not yet exist, show no dead navigation link.

Update:
- model/migration;
- services/selectors/permissions/serializers/views;
- user-management UI and Persian labels;
- OpenAPI/API contract;
- entity/relationship/ERD documentation as applicable;
- KARIZ_PROJECT_HANDOFF.md continuously.

Tests must cover:
- migration/default/backfill;
- database constraint;
- all four roles and every approved workstream/profile;
- login/profile/inactive-user behavior;
- own-profile identity mutation rejection;
- authorized and unauthorized user administration;
- direct-ID and custom-action access;
- privilege escalation/server fields;
- sales API isolation for after-sales operators;
- browser navigation desktop/mobile;
- audit safety;
- no seat-limit behavior at application level.

Run targeted tests first, then:
- python manage.py check --settings=config.test_settings
- python manage.py makemigrations --check --dry-run --settings=config.test_settings
- python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
- python manage.py test --settings=config.test_settings -v 1
- python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
- node --check common/static/common/kariz-app.js
- python scripts/check_html_branding.py
- git diff --check
- git diff --stat

Mandatory handoff protocol:
- Update KARIZ_PROJECT_HANDOFF.md after schema, backend authorization, UI, and test subtasks separately.
- Record files, migration/data impact, endpoints/routes, authorization matrix, commands/results, assumptions, blockers, current commit/status, and exact next action.
- If any test fails or the session stops, persist the exact failing command and resume point before stopping.

Stop after C1-2 is green.

Output exactly:
DONE or BLOCKED_DECISION or FAILED | migration | authorization matrix | tests | blockers | next phase
```

---

# C1-3 — Operational sales document, geography, and postal workflow

```text
Work directly in the curated Kariz CRM repository.

Read and obey first:
- AGENTS.md
- BACKEND_SPEC.md
- KARIZ_PROJECT_HANDOFF.md
- approved Client-1 invoice/order/postal decisions from C1-1
- current Sale/Customer/Product/Lead services and authorization
- relevant backend and UI contracts/tests

Do not inspect unrelated vendor/minified files. Do not create another roadmap/status file. Do not commit automatically. Do not run destructive Git commands.

Goal:
Implement the approved operational sales-document model and the city/province and postal-status reports without inventing legal/accounting semantics.

Fail closed:
- If C1-1 did not decide whether to extend Sale or create a separate internal order/document, stop with BLOCKED_DECISION.
- Do not choose an entity architecture based on the initial screenshot alone.
- Do not implement tax, fiscal invoice rules, payment, ledger, discount, inventory, carrier API, PDF, or accounting numbering unless they are explicitly approved with acceptance criteria.

Implement exactly the approved contract, including as applicable:
- relationship to existing Sale/Customer/Product;
- line-item cardinality if approved;
- server-owned customer/seller/geography values;
- province/city snapshot for historical reporting when approved;
- document date and cancellation/correction semantics;
- exact bounded postal-status choices;
- dedicated transactional status transition service;
- tracking code rules;
- append-only postal history only if approved, otherwise safe audit of current-status transitions;
- no ordinary hard deletion;
- indexes and database constraints for integrity and reporting.

Authorization:
- sales operators may access only documents in their approved Sale/Lead scope;
- after-sales operators receive only the minimum approved read access, if any;
- elevated roles receive only the approved company scope;
- identity, snapshots, totals, ownership, state, and audit fields are server-controlled;
- direct-ID access outside scope returns the established safe response.

Expose versioned APIs and maintained Persian RTL pages using the existing first-party shell and same-origin CSRF client. Do not reuse demo JavaScript or fake success handlers.

Implement predefined reports with exact approved semantics:
- document count grouped by province and city;
- document count grouped by current postal status;
- approved date range and document-status filters;
- identical authorization for UI/JSON/XLSX if export is approved;
- bounded, deterministic results and explicit empty/error states.

Update:
- models/migrations/services/selectors/serializers/views/URLs;
- first-party UI/navigation;
- OpenAPI/API contract;
- entity catalog/relationships/ERD;
- BACKEND_SPEC only if implementation reveals a confirmed contract clarification;
- KARIZ_PROJECT_HANDOFF.md after every coherent task.

Tests must cover:
- migration/preflight/backfill behavior;
- database constraints;
- transactional creation and rollback;
- historical snapshot immutability;
- cancellation/correction restrictions;
- postal transition validation and audit;
- role/workstream scope and direct-ID attacks;
- server-field mass-assignment rejection;
- city/province and postal report formulas/filters;
- query bounds/query growth;
- Persian desktop/mobile browser flows;
- CSRF, conflict, throttle, 403/404, empty/loading/error states.

Run targeted tests first, then the complete repository gates:
- python manage.py check --settings=config.test_settings
- python manage.py makemigrations --check --dry-run --settings=config.test_settings
- python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
- python manage.py test --settings=config.test_settings -v 1
- python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
- node --check common/static/common/kariz-app.js
- python scripts/check_html_branding.py
- git diff --check
- git diff --stat

Mandatory handoff protocol:
- Update KARIZ_PROJECT_HANDOFF.md after schema, services/API, reports, UI, and verification subtasks.
- Record data impact, migrations, endpoints/routes, authorization, exact report semantics, tests/results, blockers, current commit/status, and exact next action.
- Never mark the legal/accounting invoice domain complete unless that exact approved scope exists and passes.

Stop after C1-3.

Output exactly:
DONE or BLOCKED_DECISION or FAILED | data model | migrations | reports | tests | blockers | next phase
```

---

# C1-4 — Contact-status reporting and detailed user performance

```text
Work directly in the curated Kariz CRM repository.

Read and obey first:
- AGENTS.md
- BACKEND_SPEC.md
- KARIZ_PROJECT_HANDOFF.md
- approved Client-1 incoming-number/contact-status/performance definitions from C1-1
- current Lead/Interaction/Customer/Sale/report selectors, services, APIs, UI, and tests

Do not inspect unrelated vendor/minified files. Do not create another roadmap/status file. Do not commit automatically. Do not run destructive Git commands.

Goal:
Implement the approved “incoming numbers by contact status” report and detailed management performance without publishing ambiguous metrics.

Fail closed:
- If the counted unit, deduplication rule, current-status derivation, time basis, outcome list, or metric formulas are not APPROVED, mark only that slice BLOCKED_DECISION and continue independent approved work.
- Do not reinterpret “incoming number” as Lead, CustomerPhone, Interaction, SMS sender, or call unless the approved contract says so.
- Do not silently convert existing free-text values to invented codes.

Implement the approved contact-status contract:
- bounded application choices and database constraint only if approved;
- migration preflight that detects incompatible historical values and fails clearly without rewriting/deleting them;
- deterministic current-status selector, including exact tie-break ordering and no-contact state if approved;
- count each approved reporting unit exactly once;
- approved date/source/campaign/product/user filters;
- role/object scope identical across UI/API/export.

Implement the approved detailed performance report while preserving existing canonical metrics unless the contract explicitly changes them. Add only approved metrics, for example:
- customers_created_count;
- interactions_count;
- sales_count;
- sales_amount;
- average_sale_amount;
- any other metric only with an exact numerator, denominator, period field, cancellation rule, and reassignment policy.

Provide bounded drill-down to the exact approved underlying records. Reuse existing authorization selectors instead of duplicating scope logic.

Authorization:
- ordinary operators see only their approved own scope;
- after-sales operators do not receive sales-performance data unless approved;
- manager/IT/platform visibility follows the approved matrix;
- query parameters cannot bypass scope;
- direct IDs outside scope remain hidden safely.

Build/update maintained Persian RTL management UI with:
- summary table/cards;
- contact-status distribution;
- date/user/product/campaign filters only when approved;
- drill-down;
- loading/empty/validation/403/404/409/429/network states;
- desktop/mobile/keyboard behavior.

Preserve JSON/XLSX parity for every approved exported result. Maintain formula-injection defenses and deterministic column order.

Update contracts/docs and KARIZ_PROJECT_HANDOFF.md continuously.

Tests must cover:
- migration preflight and incompatible legacy values;
- deterministic latest/current-status behavior;
- no-contact and tie cases;
- deduplication/counting unit;
- every metric formula, zero denominator, cancelled-record handling, and time boundary;
- role/workstream/direct-ID/filter attacks;
- JSON/XLSX parity and workbook validity;
- query bounds/query growth;
- browser flows and error states.

Run targeted tests first, then:
- python manage.py check --settings=config.test_settings
- python manage.py makemigrations --check --dry-run --settings=config.test_settings
- python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
- python manage.py test --settings=config.test_settings -v 1
- python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
- node --check common/static/common/kariz-app.js
- python scripts/check_html_branding.py
- git diff --check
- git diff --stat

Mandatory handoff protocol:
- Update KARIZ_PROJECT_HANDOFF.md after contact contract, report selector/API, drill-down/export, UI, and tests.
- Record exact formulas and counted units, migrations, endpoints, scope, commands/results, blockers, current commit/status, and exact next action.

Stop after C1-4.

Output exactly:
DONE or PARTIAL_BLOCKED or FAILED | contact report | performance report | tests | blockers | next phase
```

---

# C1-5 — After-sales panel

```text
Work directly in the curated Kariz CRM repository.

Read and obey first:
- AGENTS.md
- BACKEND_SPEC.md
- KARIZ_PROJECT_HANDOFF.md
- approved Client-1 after-sales contract from C1-1
- approved identity/workstream implementation from C1-2
- approved sales-document relationship from C1-3
- current audit/error/request/authorization conventions

Do not inspect unrelated vendor/minified files. Do not create another roadmap/status file. Do not commit automatically. Do not run destructive Git commands.

Goal:
Implement the minimal approved after-sales workflow and panel with strict separation from sales operations.

Fail closed:
- If required fields, statuses, transitions, assignment rules, customer/order relationship, creator permissions, or manager scope are not approved, stop that slice with BLOCKED_DECISION.
- Do not invent SLA, refund, return, attachment, notification, ticket, FAQ, payment, or automation behavior.

Implement the approved domain, which may include:
- required Customer;
- optional/required approved sales document or Sale relationship;
- subject and bounded description;
- exact approved status choices;
- assigned operator;
- creator;
- server-owned closed/resolved timestamps;
- created/updated timestamps;
- indexes and database constraints.

Consistency:
- when a sales document is supplied, derive and validate Customer according to the approved contract;
- assigned operator must be an active eligible after-sales identity;
- identity/assignment/status/timestamps are server-controlled;
- multi-row transitions are transactional;
- normal workflows do not hard-delete cases.

Authorization:
- after-sales operators see and change only approved assigned/created cases;
- sales operators cannot access after-sales APIs unless approved;
- manager/IT/platform scope follows the approved matrix;
- reassignment uses a dedicated audited action/service;
- status changes use a dedicated service/action;
- direct-ID and filter attacks fail safely.

Expose only the minimum approved Customer/document lookup to after-sales operators. Do not grant unrestricted sales Customer/Lead/Sale APIs as a shortcut.

Build maintained Persian RTL pages for the approved flows, typically:
- case list;
- case create;
- case detail;
- status transition;
- manager assignment/reassignment.

Navigation must reflect real permissions and must not contain dead links.

Audit safely:
- create;
- assignment/reassignment;
- status transition;
- close/reopen only if approved.
Never log raw description/body/private payloads.

Update models/migrations/services/selectors/serializers/views/URLs/UI/OpenAPI/contracts/entity docs/ERD and KARIZ_PROJECT_HANDOFF.md continuously.

Tests must cover:
- migration/constraints;
- customer/document consistency;
- eligible assignee rules;
- every approved transition;
- rollback and audit safety;
- role/workstream/direct-ID/filter attacks;
- server-field rejection;
- inactive users;
- CSRF/throttle/conflict/not-found;
- Persian desktop/mobile browser flows and navigation.

Run targeted tests first, then the complete repository gates:
- python manage.py check --settings=config.test_settings
- python manage.py makemigrations --check --dry-run --settings=config.test_settings
- python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
- python manage.py test --settings=config.test_settings -v 1
- python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
- node --check common/static/common/kariz-app.js
- python scripts/check_html_branding.py
- git diff --check
- git diff --stat

Mandatory handoff protocol:
- Update KARIZ_PROJECT_HANDOFF.md after schema, workflow services, authorization/API, UI, and tests.
- Record migrations/data impact, endpoints/routes, transitions, scope, commands/results, blockers, current commit/status, and exact next action.

Stop after C1-5.

Output exactly:
DONE or BLOCKED_DECISION or FAILED | migrations | workflow | authorization | tests | blockers | next phase
```

---

# C1-6 — Inbound SMS foundation and reporting

```text
Work directly in the curated Kariz CRM repository.

Read and obey first:
- AGENTS.md
- BACKEND_SPEC.md
- KARIZ_PROJECT_HANDOFF.md
- approved Client-1 SMS contract from C1-1
- official provider documentation supplied by the user, if available
- existing phone normalization, request bounds, audit, logging, and security code

Do not inspect unrelated vendor/minified files. Do not create another roadmap/status file. Do not commit automatically. Do not run destructive Git commands.

Goal:
Implement a provider-neutral, secure inbound-SMS foundation and the approved count-by-day/hour report. Implement a live provider adapter only from official documentation.

Fail closed:
- If official provider authentication/signature and payload documentation are unavailable, do not invent a public webhook and do not expose an unsigned generic ingestion endpoint.
- In that case, implement only the approved internal storage/service/report boundary, mark live integration BLOCKED_EXTERNAL, and continue repository-controlled work.
- Do not implement outbound SMS unless explicitly approved.
- Do not retain message body/content unless the approved contract requires it and defines retention/access.

Implement the approved minimal record, typically including:
- provider code;
- provider message ID/idempotency key;
- normalized sender number where applicable;
- recipient/service identifier only if required;
- received timestamp;
- created timestamp;
- optional approved metadata with strict allowlisting and bounds.

Requirements:
- transactional idempotent ingestion;
- unique provider/message constraint;
- replay protection according to provider docs;
- exact signature/authentication verification for a live adapter;
- bounded payload size/depth/fields;
- timezone-aware received_at;
- approved Asia/Tehran grouping and approved Jalali/Gregorian presentation;
- no secrets, signatures, message body, or raw private payload in logs/audit;
- safe synthetic fixtures only.

Implement the approved management report:
- inbound SMS count by local date and hour;
- approved date range/provider/recipient filters;
- deterministic timezone conversion, including day boundaries;
- bounded results;
- exact approved role access;
- Persian RTL UI with loading/empty/error states.

If provider docs are available, implement only the documented adapter and add authentication, replay, duplicate, malformed payload, clock-skew, and rate-limit tests. Never print or commit credentials.

Update models/migrations/services/adapter boundary/API/UI/OpenAPI/contracts/entity docs and KARIZ_PROJECT_HANDOFF.md continuously.

Tests must cover:
- idempotency and concurrency-safe duplicate handling;
- database uniqueness;
- phone normalization;
- timezone/date/hour aggregation and boundary cases;
- role/direct-ID/filter scope;
- payload limits;
- signature/authentication/replay when adapter exists;
- audit/log redaction;
- browser report behavior.

Run targeted tests first, then:
- python manage.py check --settings=config.test_settings
- python manage.py makemigrations --check --dry-run --settings=config.test_settings
- python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
- python manage.py test --settings=config.test_settings -v 1
- python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
- node --check common/static/common/kariz-app.js
- python scripts/check_html_branding.py
- git diff --check
- git diff --stat

Mandatory handoff protocol:
- Update KARIZ_PROJECT_HANDOFF.md after storage/service, provider boundary/adapter, report, UI, and verification.
- Record provider status as PASS, BLOCKED_EXTERNAL, or FAILED; record no secret values.
- Record migrations, endpoints/routes, authorization, commands/results, current commit/status, blockers, and exact next action.

Stop after C1-6 repository work.

Output exactly:
DONE or BLOCKED_EXTERNAL or FAILED | storage/report | provider adapter | tests | blockers | next phase
```

---

# C1-7 — Unified Client-1 dashboard and active-UI hardening

```text
Work directly in the curated Kariz CRM repository.

Read and obey first:
- AGENTS.md
- BACKEND_SPEC.md
- KARIZ_PROJECT_HANDOFF.md
- every approved Client-1 capability and implementation evidence from C1-2 through C1-6
- active first-party UI routes/templates/static files/tests

Do not add new business domains. Do not inspect or mass-edit unrelated vendor/minified files. Do not create another roadmap/status file. Do not commit automatically. Do not run destructive Git commands.

Goal:
Integrate the seven approved Client-1 capabilities into one coherent Persian RTL application shell and management dashboard, then remove active dead/demo behavior.

Build only from approved backend selectors/services/APIs. Every displayed number must use the same authorization and semantics as its API/export.

The dashboard/navigation must expose only implemented, authorized capabilities, such as:
- sales operations;
- after-sales operations;
- detailed user performance and drill-down;
- inbound SMS by day/hour;
- sales-document count by province/city;
- incoming-number/contact-status distribution;
- sales documents by postal status.

Role/workstream navigation and direct URL access must match the approved matrix. Frontend hiding is never the only control.

No application seat limit may be introduced. Do not claim infinite concurrency; show no such marketing claim in UI.

Audit every active reachable first-party route and control. Remove or hide from the active application:
- dead links/buttons;
- action="#";
- fake success;
- demo records/notifications;
- vendor purchase/preview/demo links;
- public signup;
- dynamic role builders;
- future modules without real backend;
- hard-delete wording where the workflow deactivates/cancels.

Do not mass-delete theme/vendor resources. Do not rename KTMenu, KTDrawer, KTUtil, data-kt-* or stable runtime identifiers unless a bounded dependency removal has been proven and tested.

Verify:
- Persian and RTL;
- desktop/mobile responsiveness;
- keyboard/focus basics;
- loading/empty/validation/conflict/throttle/permission/not-found/network states;
- no browser console errors;
- no failed first-party network requests;
- no broken navigation;
- no secret or customer data in client logs;
- consistent branding.

Create/update a Client-1 capability matrix in KARIZ_PROJECT_HANDOFF.md. For every capability, record:
- contract status;
- backend status;
- UI status;
- automated-test status;
- PostgreSQL/runtime status;
- target-site/UAT status;
- remaining blocker.
Do not mark VERIFIED_END_TO_END before C1-8/C1-9 evidence exists.

Run:
- targeted browser suites for every role/workstream and capability;
- python manage.py check --settings=config.test_settings
- python manage.py makemigrations --check --dry-run --settings=config.test_settings
- python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
- python manage.py test --settings=config.test_settings -v 1
- python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
- node --check common/static/common/kariz-app.js
- python scripts/check_html_branding.py
- applicable dependency/source/security checks documented in docs/ops
- git diff --check
- git diff --stat

Mandatory handoff protocol:
- Update KARIZ_PROJECT_HANDOFF.md after navigation/dashboard, each capability UI integration, cleanup batches, browser verification, and final repository gate.
- Record exact files/routes, capability matrix, commands/results, blockers, current commit/status, and exact next action.
- If a cleanup candidate cannot be proven unused, leave it and record it; do not guess-delete.

Stop after repository/UI completion.

Output exactly:
DONE or PARTIAL_BLOCKED or FAILED | capability matrix summary | tests | blockers | next phase C1-8
```

---

# C1-8 — Production-like PostgreSQL/Docker/Nginx/backup proof

```text
Work directly in the curated Kariz CRM repository on an approved disposable/staging host with no production customer data.

Read and obey first:
- AGENTS.md
- KARIZ_PROJECT_HANDOFF.md
- docs/ops/DEPENDENCIES.md
- docs/ops/DEPLOYMENT.md
- docs/ops/DEPLOYMENT_BOOTSTRAP.md
- docs/ops/DATABASE_ROLES.md
- docs/ops/BACKUP_RESTORE.md
- docs/ops/ROLLBACK.md
- docs/ops/LOAD_TEST.md
- docs/ops/SECURITY_SCANS.md
- docs/ops/RELEASE_CHECKLIST.md
- docs/ops/UAT.md

Do not invent new release procedures when a reviewed runbook exists. Do not commit automatically. Do not run destructive Git commands.

Safety boundary:
- Use only an explicitly approved disposable database, volume, compose project, backup path, and host.
- Never reset/delete/overwrite an unknown database, volume, backup, image, network, or customer data.
- Start with read-only environment discovery.
- If the environment identity or approval is unclear, update KARIZ_PROJECT_HANDOFF.md with BLOCKED_EXTERNAL and stop before mutation.

Record the preflight:
- OS/version and architecture;
- CPU/RAM/free disk;
- Docker Engine and Compose versions;
- PostgreSQL client/server availability;
- browser/driver availability;
- ports in use;
- exact Git commit;
- exact reviewed image digests/config source;
- disposable project/database/volume identities without secrets.

If required tooling, image digests, secret inputs, hostname, or safe disposable resources are missing, do not fabricate them. Record the exact prerequisite and continue only independent read-only checks.

Using existing scripts/runbooks, prove on the exact release as applicable:
1. native PostgreSQL migration from empty database;
2. migration upgrade/re-run behavior;
3. PostgreSQL-specific constraints and concurrency tests;
4. least-privilege database roles;
5. compose config validation;
6. reviewed image/digest validation;
7. stack boot;
8. one-shot migration behavior;
9. collectstatic/static delivery;
10. live and ready health endpoints;
11. authenticated API smoke;
12. every approved role/workstream smoke;
13. all seven Client-1 workflows using synthetic data;
14. write-stop on/off behavior;
15. restart and readiness recovery;
16. bounded/rotated logs;
17. Nginx proxy/request-ID/header behavior;
18. real PostgreSQL backup;
19. checksum validation;
20. restore into a new isolated disposable database with no application network access during restore verification;
21. approved safe load test with explicit target and abort rule;
22. applicable dependency/source/container/TLS scans.

Do not claim TLS success without a real approved hostname and certificate path. Do not print secrets. Do not store customer personal data in test evidence.

Run real browser smoke against the running stack for every approved role/workstream on desktop and mobile. Capture command-level evidence, not unsupported claims.

Mandatory handoff protocol:
- Update KARIZ_PROJECT_HANDOFF.md after every runtime gate, not only at the end.
- For each external gate use PASS, FAILED, or BLOCKED_EXTERNAL.
- Record exact command, exit/result, artifact identifier/checksum/digest without secrets, rollback point, owner/blocker, and exact next action.
- If a destructive risk or unexpected environment identity appears, stop and persist the resume point immediately.

Do not label the release production ready unless all repository-controlled and required external gates genuinely pass. The correct intermediate label remains “production candidate; external verification pending”.

Output exactly:
STATUS | passed runtime gates | failed gates | external blockers | rollback point | exact next action
```

---

# C1-9 — Target-site deployment, UAT, and controlled cutover

```text
Work from the exact tested Client-1 release and follow the repository runbooks.

Read and obey first:
- AGENTS.md
- BACKEND_SPEC.md
- KARIZ_PROJECT_HANDOFF.md
- docs/ops/DEPLOYMENT.md
- docs/ops/DEPLOYMENT_BOOTSTRAP.md
- docs/ops/BACKUP_RESTORE.md
- docs/ops/ROLLBACK.md
- docs/ops/INCIDENT_RESPONSE.md
- docs/ops/RELEASE_CHECKLIST.md
- docs/ops/UAT.md
- approved Client-1 acceptance matrix

Do not commit automatically. Do not run destructive Git commands. Do not expose secrets in output or handoff.

Start READ-ONLY on the client site.

Collect and record:
- exact server OS/version and architecture;
- CPU/RAM/disk layout/free space;
- virtualization/container support;
- router/firewall/VPN topology;
- static public IP or CGNAT condition;
- production hostname/DNS ownership;
- TLS certificate and renewal owner;
- expected total and peak concurrent users;
- UPS/power condition;
- backup destination, off-host copy, retention, RPO/RTO, and owner;
- SMS-provider network requirements;
- maintenance/cutover/rollback owners and approved window.

Do not change the client's router, firewall, network interfaces, production database, server services, or data until the target design, rollback point, and owner approval are recorded.

Security target:
- prefer individual VPN identity with MFA for remote administration/access where appropriate;
- expose only approved HTTPS service through Nginx;
- keep PostgreSQL, application server, SSH/RDP/admin/database ports private and restricted;
- use protected environment secrets and least privilege.

After explicit approval:
- deploy the exact C1-8-tested commit/images/digests;
- establish rollback point and pre-change backup;
- configure secrets without printing them;
- run migrations using the approved release procedure;
- bootstrap/confirm the Platform Admin through the approved method;
- verify health/readiness/static/auth/CSRF/cookies/request IDs;
- verify TLS/redirect/HSTS and closed forbidden ports;
- verify service restart/recovery;
- run backup, off-host copy, checksum, and isolated restore;
- verify logging/monitoring/alert ownership;
- run production-shaped safe load smoke within the approved target/abort rule.

Run formal UAT with approved non-secret or synthetic data for every Client-1 capability:
- sales panel;
- after-sales panel;
- detailed user performance/drill-down;
- inbound SMS day/hour report;
- sales-document count by province/city;
- incoming-number/contact-status report;
- sales documents by postal status.

Test every approved role/workstream, direct-ID isolation, desktop/mobile, errors, export if approved, and recovery/rollback procedures.

Record in KARIZ_PROJECT_HANDOFF.md:
- release commit and image digests;
- migration heads;
- environment/profile;
- UAT cases and results;
- backup identifier/checksum without secrets;
- rollback point;
- owners/sign-off;
- training/handover status;
- unresolved risks and exact remaining actions.

Mark a capability VERIFIED_END_TO_END only when its target-site acceptance and required runtime evidence pass. Otherwise keep the exact capability blocked; never fake completion.

Mandatory handoff protocol:
- Update KARIZ_PROJECT_HANDOFF.md after survey, approval, backup/rollback point, deployment, each verification group, UAT, and sign-off.
- If any safety or acceptance gate fails, record the exact failure and use the approved rollback/abort procedure.

Output exactly:
RELEASE STATUS | verified capabilities | blocked capabilities | UAT result | rollback point | exact remaining action
```

---

## Files/information to collect

### Needed for C1-1 tomorrow

- The customer's final detailed requirement list.
- Any customer annotations or examples that clarify the seven initial items.

### Strongly useful before C1-3/C1-5

- One redacted sample of the current invoice/order/sales document.
- Exact postal statuses and who changes them.
- One redacted sample of the desired detailed performance report.
- Exact meaning and source of “incoming numbers”.
- After-sales workflow example from opening through closing.

### Needed for a live C1-6 provider adapter

- SMS provider name.
- Official API/webhook documentation or PDF.
- Authentication/signature rules.
- Idempotency/message identifier rules.
- Sanitized sample request/response with no credentials or real customer content.

### Needed for C1-8/C1-9

- Approved staging/target OS and server specifications.
- Expected peak concurrent users and load-test abort rule.
- Domain/DNS/TLS plan.
- Router/firewall/VPN information.
- Backup destination, off-host destination, retention, owner, RPO/RTO.

## Immediate instruction

Run **C1-1 decision closure only** now for C1-DEC-GOV-001, SEAT-001, TEAM-001, and AFTER-001. The four fixed User Management roles are confirmed. Then rerun the C1-2 preflight. Do not create workstream/schema feature code before that gate is green.

## Lead Management decision checkpoint - 2026-08-11

- Requested scope: priority, archive, conversion workflow, Opportunity, and Pipeline stages while preserving existing Lead behavior.
- Gate result: `BLOCKED_DECISION`; no expansion code, migration, endpoint, permission, UI, or architecture change was made.
- Authority evidence: `BACKEND_SPEC.md` marks the final Lead status list and the full conversion/priority/archive/Opportunity/Pipeline contracts unresolved. Provisional status candidates are not approved values.
- The required pre-code decision section is recorded in `KARIZ_PROJECT_HANDOFF.md` section 27. It separates final status approval, allowed transition matrix, conversion rules, priority semantics, archive behavior, Opportunity schema, and Pipeline/stage lifecycle.
- Existing approved Lead CRUD/scope, manual reassignment/history, backend-owned opaque status, and no-hard-delete behavior stay unchanged.
- Exact unblock input: named sales-process owner; final codes/labels and transition matrix; role/owner rules; conversion target/cardinality/idempotency/rollback; priority scale/default/order; archive/reopen/visibility rules; Opportunity fields/relations; Pipeline/stage order/history/forecast rules; legacy-value mapping; acceptance examples.
- Next implementation order after approval: data preflight and additive migration; models/constraints; transactional services/audit; selectors/permissions; serializers/actions/schema; maintained Persian RTL UI; API/browser/concurrency/regression proof.

## Interaction Management decision checkpoint - 2026-08-11

- Included target: interaction timeline, follow-up tasks, meetings, calendar view, assigned responsible person, and due dates.
- Explicitly excluded: telephony integration, call recording, and automatic reminders. These remain separate-service work.
- Gate result: `BLOCKED_DECISION`; inclusion is confirmed, but entity shape, task/meeting lifecycle, responsible-user rules, due-date/timezone semantics, timeline sources/order, calendar contract, authorization, audit, and acceptance examples are not approved.
- Existing append-only manual Interaction behavior, `agent` as recorder, optional `next_follow_up_at`, Lead-bound backend scope, and active APIs/UI remain unchanged.
- No model, migration, endpoint, permission, UI route/template, CSS, scheduler, provider adapter, or architecture change was made.
- Exact decisions and unblock examples are recorded in `KARIZ_PROJECT_HANDOFF.md` section 28.
- Next implementation order after approval: additive models/migration; transactional services/audit; selectors/permissions; API/schema; maintained Persian RTL timeline/task/meeting/calendar UI; isolation/time-boundary/concurrency/browser regression proof.

## Product Management Phase 1 checkpoint - 2026-08-11

- Phase result: `PARTIAL`.
- Done: optional exact `is_active=true|false` Product list filter; scope-first active/inactive isolation; Persian list filter; SKU form bound aligned to backend maximum 80; focused API/UI/schema tests.
- Proof: focused suite 25/25 PASS; full suite 283 with 6 skips PASS; real Product browser filter flow 2/2 PASS on rerun; system/migration/schema/static/branding/diff gates PASS.
- Compatibility: existing Product fields, create/edit/deactivate, role matrix, search/order/page, current price, and immutable Sale snapshots remain unchanged. No migration or new endpoint.
- Blocked: Category entity and category filter need flat/tree, fields, uniqueness, lifecycle, linked-Product, migration, authorization, audit, UI, and acceptance decisions.
- Blocked: “better product forms” needs an exact added-field list and validation contract. Only the proven SKU bound mismatch was changed.
- `FINAL_WAVE_LOW`: inventory, stock, purchase cost, multi-price, discount, profit calculation, and reports remain required last-wave work. No schema or behavior was added.
- Architecture boundary: keep Product as catalog/current-price identity; preserve Sale snapshots; design stock movement, cost/price history, discount policy, and profit formula only after their separate contracts are approved.
- Next Phase 1 step after approval: Category additive model/lifecycle, scoped services/API/filter, maintained form/list UI, migration preflight, and role/direct-ID/browser regression tests.

## Sales expansion pre-model checkpoint - 2026-08-11

### Shared gate

- Confirmed: separate Order, Quotation, Invoice, Payment, and Customer Account modules; no ordinary hard delete; audited financial mutations; PDF deferred; tax contract required before tax/Invoice calculation implementation.
- Existing Sale remains separate and unchanged.
- Gate result: `BLOCKED_DECISION`; shared relations, line items, money/rounding, numbering, roles, dates, lifecycles, import/reconciliation, acceptance, and phase-priority decisions are missing.
- Tax precondition: jurisdiction, taxable base, rates/effective dates, included/excluded behavior, exemptions, discount order, rounding, immutable snapshots, corrections, fiscal fields, and expected totals must be approved before Invoice/money schema or formulas.
- No app/module scaffold, model, migration, API, UI, permission, PDF, tax, or provider code was created.
- Full pre-model decision record is in `KARIZ_PROJECT_HANDOFF.md` section 30.

### Order module checkpoint

- State: `BLOCKED_DECISION`.
- Missing: meaning/source, Customer/Lead/Sale links, items, statuses/transitions, approval, fulfillment, partial/cancel/correct, numbering, totals, future stock effect.
- Roadmap update complete; implementation not started.

### Quotation module checkpoint

- State: `BLOCKED_DECISION`.
- Missing: relation, revisions, validity/expiry, item snapshots, accept/reject/withdraw, approval, numbering, conversion/idempotency.
- Roadmap update complete; implementation not started.

### Invoice module checkpoint

- State: `BLOCKED_DECISION`.
- Missing: legal/accounting meaning, source relation, items, issue/void/correct, numbering, due date, amount equations, approved tax rules, allocation, historical snapshots.
- PDF remains later. Roadmap update complete; implementation not started.

### Payment module checkpoint

- State: `BLOCKED_DECISION`.
- Missing: source/methods, currency, Invoice allocation, partial/overpayment, states, idempotency, reference, reversal/refund, reconciliation.
- Roadmap update complete; implementation not started.

### Customer Account module checkpoint

- State: `BLOCKED_DECISION`.
- Missing: ledger versus derived view, debit/credit convention, event sources, opening balance, currency, adjustment/reversal, balance equation, statements, visibility.
- Roadmap update complete; implementation not started.

### Resume rule

- Resolve shared decisions and tax documentation first. Then build one approved module at a time with additive migrations, transactional services, audit, selectors/permissions, API/schema, maintained Persian RTL UI, database/concurrency/security/browser tests, and a roadmap/handoff update after that module.
