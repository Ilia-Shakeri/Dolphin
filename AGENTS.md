AGENTS.md — Kariz CRM

Authority order

BACKEND_SPEC.md

KARIZ_PROJECT_HANDOFF.md for live status, completed work, assumptions, blockers, and next commands

Applicable AGENTS.md / AGENTS.override.md

Existing code when it conforms to the sources above

Never infer business rules, entities, statuses, permissions, financial behavior, or workflows from Metronic demo pages. Record unclear rules in `KARIZ_PROJECT_HANDOFF.md`.

Working directory

Work only inside the curated Kariz CRM repository. Do not inspect a parent directory containing the full Metronic/vendor archive. Treat reference/vendor material as read-only.

Read scope

Read first:

BACKEND_SPEC.md
KARIZ_PROJECT_HANDOFF.md
manage.py
backend/**/*.py
config/**/*.py
*/migrations/*.py
*/tests/**/*.py
requirements*.txt
pyproject.toml
pytest.ini
Dockerfile*
compose*.yml
nginx/**
.env.example

For frontend contracts, inspect only the exact auth, customer/contact, user-management, dashboard, and explicitly approved support files named in the specification or handoff. Read large HTML/context files in bounded ranges after locating relevant forms, fields, tables, filters, and actions with rg -n.

Do not run unrestricted find ., tree, rg --files ., whole-repository indexing, or mass file reads.

Never read or modify

node_modules/
vendor/
dist/
build/
.next/
.cache/
assets/plugins/
src/plugins/
assets/media/
src/media/
fonts/
assets/css/
src/sass/
src/js/components/
src/js/layout/
src/js/vendors/
src/js/widgets/
asides/
dashboards/
layouts/
pages/
toolbars/
widgets/
utilities/
apps/ecommerce/
apps/chat/
apps/inbox/
apps/file-manager/
apps/subscriptions/
apps/calendar.html
apps/projects/
apps/invoices/
account/referrals.html
account/billing.html
account/statements.html
account/api-keys.html
*.min.js
*.bundle.js
*.chunk.js
*.map
package-lock.json
yarn.lock
pnpm-lock.yaml
composer.lock
poetry.lock
*.png
*.jpg
*.jpeg
*.svg
*.ico
*.woff
*.woff2
*.ttf
*.pdf
*.zip
*.db
*.sqlite

The specifically allowlisted authentication page under authentication/layouts/corporate/ is an exception to the generic layouts/ exclusion.

Curated frontend reference exceptions

The following exact first-party theme HTML files may be inspected read-only, in bounded ranges, only as visual/layout/UX references for their named maintained screens. They do not define business rules, permissions, data contracts, statuses, or workflows:

index.html
authentication/layouts/corporate/sign-in.html
apps/user-management/users/list.html
apps/user-management/users/view.html
dashboards/store-analytics.html
dashboards/call-center.html
apps/customers/list.html
apps/customers/view.html
apps/contacts/getting-started.html
apps/contacts/add-contact.html
apps/contacts/edit-contact.html
apps/contacts/view-contact.html
apps/ecommerce/catalog/products.html
apps/ecommerce/catalog/add-product.html
apps/ecommerce/catalog/edit-product.html
apps/ecommerce/sales/listing.html
apps/ecommerce/sales/details.html
apps/ecommerce/sales/add-order.html
apps/ecommerce/sales/edit-order.html
dashboards/finance-performance.html
apps/ecommerce/reports/sales.html
apps/ecommerce/reports/view.html

These exact files are narrow exceptions to the `dashboards/` and `apps/ecommerce/` exclusions above. No containing directory is generally allowlisted. All plugin, media, font, minified/bundled, generated/build, dependency, vendor-internal, and secret exclusions remain in force. If no exact reference is allowlisted for a maintained screen, record that gap instead of inspecting another theme tree or redesigning the screen.

Never read or commit:

.env
.env.production
.env.local
credentials.json
service-account.json
*.pem
*.key
*.p12
*.pfx

Architecture constraints

Django + Django REST Framework + PostgreSQL.

Modular monolith.

Same-origin Django Session Authentication + CSRF unless BACKEND_SPEC.md overrides it.

Versioned API under /api/v1/.

Fixed CRM roles: sales_agent, sales_manager, company_it, platform_admin.

CRM roles are separate from is_staff, is_superuser, Django groups, and server access.

Backend queryset/object authorization is mandatory; frontend-hidden buttons are not security.

Use services for assignment, reassignment, Sale creation/cancellation, role changes, and other business transitions.

Deactivate/cancel historical business records instead of ordinary hard deletion.

Audit sensitive actions without storing secrets.

Do not add JWT, Redis, Celery, microservices, Kubernetes, or dynamic permission builders without an explicit requirement.

Scope guardrails

Core V1 is centered on:

User
Customer
CustomerPhone
Lead
LeadAssignmentHistory
Interaction
Product
Sale
ActivityLog
predefined reports
XLSX export

AfterSalesRequest is optional and must follow BACKEND_SPEC.md.

Do not implement Invoice, InvoiceItem, postal status/history, external SMS, ecommerce, payment, inventory, tax, returns, refunds, shipping integration, or external synchronization until explicitly approved.

Required documentation separation

Keep these artifacts separate:

docs/backend/ENTITY_CATALOG.md
docs/backend/RELATIONSHIPS.md
docs/backend/ERD.mmd
docs/backend/API_CONTRACT.md
docs/backend/DISCOVERY.md
KARIZ_PROJECT_HANDOFF.md

Do not mix entity definitions with relationship definitions.

Change discipline

State files to inspect and change before editing.

Keep work in small, coherent, reviewable phases.

Add tests in the same phase as the behavior.

Do not broadly refactor or reformat unrelated code.

Do not use destructive Git commands.

Do not commit automatically unless explicitly requested.

Verification

Run the narrowest relevant checks, including applicable equivalents of:

python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
git diff --check
git diff --stat

End each session with files inspected/changed, migrations, endpoints, authorization rules, tests run, assumptions, blockers, and the next recommended phase.

Continuous handoff execution

When the active task is the long-running Kariz completion and production-readiness goal:

- Maintain the live phase, evidence, blockers, and exact resume point in `KARIZ_PROJECT_HANDOFF.md`.
- A task, slice, milestone, test report, or phase report is a checkpoint, not a stopping point.
- After a successful checkpoint, update the handoff and immediately begin the highest-priority unblocked task.
- Never ask the user to type `continue` for normal workspace edits, tests, documentation, safe refactors, or reviewed file deletions.
- If one item is blocked, record it in the handoff and continue independent unblocked work.
- Pause only for a real credential or secret, an irreversible external action, a data-semantic decision with no safe isolated fallback, a required sandbox approval, or when no independent unblocked work remains.
- If the session is forced to stop, persist an exact resume point in the handoff: phase, task, files, commands, evidence, and next action.

Durable codebase understanding

Maintain `KARIZ_PROJECT_HANDOFF.md` as the single root status document.

Review active first-party code subsystem by subsystem in bounded batches. Record each file's purpose, dependencies, entry points, domain impact, security concerns, tests, and branding/language status. Do not recursively consume dependency, vendor, minified, generated, build, media, font, binary, or cache trees.

Safe deletion policy

Before deleting locale, demo, duplicated, or branding-related files:

1. Ensure a safe Git/checkpoint baseline exists.
2. Produce an exact candidate manifest.
3. Prove imports, templates, and static references do not require the files.
4. Delete only a small reviewed group.
5. Run targeted checks plus relevant template, static, and browser smoke tests.
6. Restore the group if behavior regresses.

Never run broad recursive deletion, `git clean`, or `git reset --hard`.

Persian-only active application

The active Kariz user interface is Persian-only unless `BACKEND_SPEC.md` explicitly overrides it. Remove unused non-Persian locale resources and language-switch UI or behavior only after reference analysis. Preserve Persian and RTL resources, programming-language source, API/database identifiers, framework dependency locales, and required third-party notices.

Kariz branding

All user-visible and project-owned product branding must use `Kariz CRM` and the approved Persian name. Remove active vendor purchase, preview, demo links, and vendor-visible branding. Do not blindly rename stable theme runtime identifiers such as `KTMenu`, `KTDrawer`, `KTUtil`, or `data-kt-*`, and do not erase legally required third-party notices.

Verification and continuation

After each batch, run the narrowest relevant checks, inspect the diff, update handoff evidence, and continue. Run full backend, schema, and production-like checks at phase gates. Never claim production readiness without runtime and operational evidence; use `production candidate; external verification pending` when only external infrastructure proof remains.
