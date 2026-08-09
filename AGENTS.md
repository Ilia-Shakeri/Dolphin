AGENTS.md — Kariz CRM

Authority order

BACKEND_SPEC.md

Applicable AGENTS.md / AGENTS.override.md

CODEX_KARIZ_BACKEND_PROMPT.md

codex_backend_context.txt as frontend evidence only

Existing code when it conforms to the sources above

Never infer business rules, entities, statuses, permissions, financial behavior, or workflows from Metronic demo pages. Record unclear rules in ASSUMPTIONS.md.

Working directory

Work only inside the curated Kariz CRM repository. Do not inspect a parent directory containing the full Metronic/vendor archive. Treat reference/vendor material as read-only.

Read scope

Read first:

BACKEND_SPEC.md
CODEX_KARIZ_BACKEND_PROMPT.md
codex_backend_context.txt
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

For frontend contracts, inspect only the exact auth, customer/contact, user-management, dashboard, and explicitly approved support files named in CODEX_KARIZ_BACKEND_PROMPT.md. Read large HTML/context files in bounded ranges after locating relevant forms, fields, tables, filters, and actions with rg -n.

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
ASSUMPTIONS.md

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