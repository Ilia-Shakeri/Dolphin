# Kariz CRM — Backend Specification

**Document status:** Provisional authoritative implementation specification assembled from the established Kariz CRM conversation context and confirmed decisions. Newer explicit user decisions override this document.

**Product:** Kariz CRM / کاریز
**Architecture:** Django + Django REST Framework + PostgreSQL + Docker Compose + Nginx, modular monolith, Linux target
**Deployment model:** Single-tenant deployment and separate database per client company, one shared codebase

---

## 1. Interpretation rules

Every requirement in this document has one of these states:

- **CONFIRMED:** explicitly stated or accepted; implement as the current requirement.
- **WORKING ASSUMPTION:** a safe default that may be implemented only when it does not lock an unresolved business decision; record it in `KARIZ_PROJECT_HANDOFF.md`.
- **RECOMMENDED:** technical/delivery guidance, not a contractual business rule.
- **UNRESOLVED:** do not invent; isolate/defer the affected behavior and record it in `KARIZ_PROJECT_HANDOFF.md`.
- **BLOCKED:** implementation must not be claimed complete until the named decision/source exists.

Frontend labels, badges, demo data, fake submit handlers, and template pages are never authoritative business rules.

---

## 2. Product goal and V1 scope

### 2.1 Confirmed product goal

Kariz CRM is an internal sales and customer-operations CRM for companies that receive phone/SMS-originated leads, distribute work to sales agents, track manual calls/interactions and successful sales, monitor performance, and export predefined reports to XLSX.

### 2.2 Core V1 scope

- Login, logout, current-user profile, active/inactive users.
- Four fixed CRM roles with backend-enforced permissions.
- Customers with multiple normalized phone numbers.
- Leads/opportunities that allow the same Customer to re-enter by month, campaign, batch, or product context.
- Lead assignment, reassignment, assignment history, and audit.
- Manual calls/interactions and follow-up information.
- Products and current prices; read-only to Sales Agents.
- Successful Sale records with quantity, product/price snapshots, total amount, status, and timestamps.
- Predefined in-CRM reports and XLSX exports for approved/unambiguous metrics.
- Sensitive-action audit records and request IDs.
- Dockerized local/internal deployment with database-aware health checks.
- OpenAPI documentation and automated tests.

### 2.3 Optional schema-compatible scope

`AfterSalesRequest` may be implemented only when explicitly selected for the delivery scope. It requires a Customer and may optionally reference a Sale and a future Invoice.

### 2.4 Blocked implementation modules

Do not implement or claim completion for the following until a newer explicit decision defines source, creator, workflow, statuses, permissions, and acceptance criteria. Section 2.6 confirms that several families now belong to the Client-1 end target; target inclusion does not clear these implementation blocks:

- Full Invoice and InvoiceItem module.
- Invoice count/amount by city or province.
- Postal/shipping status and history.
- External SMS provider integration and trustworthy inbound SMS reporting.
- Automatic call-center/telephony integration.
- Ecommerce/order/shipping/payment/inventory/tax/return/refund modules.
- External website synchronization.

### 2.5 Out of scope by default

- Public multi-tenant SaaS.
- Microservices, Kubernetes, Redis/Celery, or complex cloud infrastructure without a concrete requirement.
- A company-facing dynamic role/permission designer.
- Implementation of all template demos/plugins/pages.
- 24/7 support or unlimited free maintenance.

Dynamic report building and dynamic role/permission design are no longer silently out of the Client-1 end target: section 2.6 records their inclusion. Both remain blocked until bounded security, authorization, data-source, workflow, and acceptance contracts exist. The fixed-role contradiction in section 4 must be resolved before any dynamic permission work.

### 2.6 Client-1 expanded target scope

**CONFIRMED target inclusion, not implementation semantics:** the final Persian Client-1 list states that every named capability family must exist in the end target. Existing repository behavior remains authoritative only where it already conforms to this specification. Template-only pages remain non-operational evidence.

Included target additions are:

- session inventory/revocation, avatar, user notifications, and user export;
- Customer classification, postal code, document relationship, export, bounded bulk operations, and aggregate profile/history;
- final Lead workflow plus priority, archive, conversion, Opportunity, and Pipeline;
- activity timeline, meetings, calendar, tasks/projects, reminders, manual specialist call reporting, and later provider-backed communication features;
- Product classification/expanded forms plus the inventory/pricing/profit family;
- Order, internal sales document, quotation, accounting Invoice, postal workflow, Payment, cheque, installment, customer account, and related reports;
- detailed performance/drill-down, visual dashboard, domain reports, profit/loss, receivables, operational PDF, and a bounded dynamic report builder;
- operational file/document management;
- global search, saved filters, and bulk XLSX import;
- workflow/automation, external website/store/gateway/accounting integrations, installable web application behavior, and abnormal-activity detection;
- real target PostgreSQL/Compose/Nginx/TLS/browser/backup/restore/load/scan/UAT proof.

The customer's explicitly marked later/low-importance additions are required but assigned to the final implementation wave:

- inventory, stock, purchase cost, multi-price, discount, profit, and inventory reporting;
- full quotation/accounting Invoice, Payment, cheque, installment, customer account, profit/loss, receivables, operational PDF, and dynamic report builder;
- operational file/document management;
- global search, saved filters, and bulk XLSX import;
- checked website/store/gateway/accounting integrations.

`FINAL_WAVE_LOW` means required and last in implementation order, not optional or delivered. Real backup scheduling/destination and recovery proof remain mandatory release gates and cannot be downgraded to optional feature work.

All new entities, statuses, transitions, formulas, role/workstream rules, report units, provider adapters, integration directions, storage policies, migrations, routes, and acceptance criteria remain **UNRESOLVED/BLOCKED** until the exact decisions recorded in `KARIZ_PROJECT_HANDOFF.md` are approved. No model, endpoint, UI route, or authorization change is authorized by target inclusion alone.

---

## 3. Authentication and identity

### 3.1 User model

Use a custom Django user model before production data exists.

Minimum business fields:

```text
username
first_name
last_name
phone
role
team nullable
is_active
last_login
created_at
updated_at
```

Rules:

- Passwords use Django secure hashing and are never returned, logged, or written to audit changes.
- CRM role is not modeled by `is_staff`, `is_superuser`, Django groups, or server access.
- Ordinary serializers must not expose writable `is_staff`, `is_superuser`, groups, direct permissions, or unrestricted role fields.
- Inactive users lose access immediately.
- No master password, shared hidden support account, or backdoor.

### 3.2 Authentication method

**RECOMMENDED:** same-origin Django Session Authentication + CSRF for the internal CRM.

External integrations, if later approved, require separate service credentials/API keys or tokens and must not use employee passwords.

---

## 4. Fixed application roles

```text
sales_agent
sales_manager
company_it
platform_admin
```

Legacy display levels 1–4 may remain only as display/backward-compatibility data. Permission checks use explicit role codes.

The Client-1 role identity and Persian display mapping is **CONFIRMED**:

- `sales_agent`: `بازاریاب (کال سنتر)`; a User and never a Customer.
- `sales_manager`: `مدیر فروشگاه`; the first client's store/sales manager.
- `company_it`: `مدیر فنی مشتری`; optional client technical administrator and never permitted to grant, target, or manage `platform_admin`.
- `platform_admin`: `مدیر پلتفرم`; reserved for the Kariz platform owner/developer/admin, highest CRM application privilege, and holder of Platform Admin custody.

Customer remains the actual store/customer/client contact and is displayed as `مشتری` / `مشتریان`. The `Customer` model, API path, database table, field names, fixed role codes, and stable internal identifiers remain unchanged.

For the single-tenant Client-1 deployment, Sales Manager scope is confirmed as company-wide for business records and all clean `sales_agent` accounts in that deployment. No Team model is created. Sales Manager may list, create, edit, deactivate, and reactivate Sales Agent accounts only; it cannot target elevated-role users or change/grant roles. Company IT manages clean non-platform identities under the existing Platform Admin ceiling. Platform Admin manages every clean CRM identity and fixed CRM role. Client-1 uses a bounded `sales` / `after_sales` workstream on Sales Agent accounts only; it does not add a fifth role or dynamic permission builder. Elevated roles must remain in `sales`. Seat/capacity remains a separate unresolved decision.

### 4.1 Access matrix

| Capability | Sales Agent | Sales Manager | Company IT | Platform Admin |
|---|---|---|---|---|
| Sign in / own profile | Yes | Yes | Yes | Yes |
| View Customers | Own/assigned only | All | All | All |
| Create Customer | Yes | Yes | Yes | Yes |
| Edit Customer | Own/assigned, allowed fields | All | All | All |
| Deactivate Customer | No | Yes | Yes | Yes |
| View Leads | Assigned or created, subject to final visibility rule | All | All | All |
| Create Lead | Yes | Yes | Yes | Yes |
| Reassign Lead | No | Yes | Yes | Yes |
| Change Lead status | Assigned Leads only | All | All | All |
| Register Interaction | Assigned Lead only | All | All | All |
| View Products | Yes | Yes | Yes | Yes |
| Manage Products | No | Yes | Yes | Yes |
| Mark Sale | Assigned Lead only | Yes | Yes | Yes |
| Correct/cancel Sale | No | Yes, audited | Yes, audited | Yes, audited |
| View own KPI | Yes | Yes | Yes | Yes |
| View company/user KPIs | No | Yes | Yes | Yes |
| Export own report | Yes | Yes | Yes | Yes |
| Export company report | No | Yes | Yes | Yes |
| Manage ordinary users | No | Sales Agent accounts only | All clean non-platform users | Every clean CRM identity |
| Assign CRM roles | No | No | Up to `company_it`; never `platform_admin` | Yes |
| Grant platform admin/superuser | No | No | No | Yes |
| View audit log | No | No | Non-platform-safe audit | All CRM audit |
| Django admin/server operations | No | No | No by default | Separately controlled |

### 4.2 Mandatory backend enforcement

- Every list/retrieve/update/delete/custom-action endpoint applies role-aware queryset scoping.
- Direct object-ID access must not expose another agent’s private object.
- Ownership/assignment/sold-by/role/admin fields are server-controlled.
- Reassignment uses a dedicated audited service/action.
- Role administration prevents horizontal and vertical privilege escalation.
- Hiding a frontend button is never authorization.

---

## 5. Domain entities

Entity definitions and relationship definitions must also be maintained separately in:

```text
docs/backend/ENTITY_CATALOG.md
docs/backend/RELATIONSHIPS.md
docs/backend/ERD.mmd
```

### 5.1 Customer

Fields:

```text
full_name
national_id nullable
email nullable
province nullable
city nullable
postal_code nullable
category nullable
address nullable
notes
created_by
is_active
created_at
updated_at
```

Rules:

- Customer represents contact identity, not one sales cycle.
- Sales Agents may create Customers and edit permitted fields only when the Customer is in their own/assigned visibility scope.
- Normal UI deactivates rather than hard-deletes Customers.
- Client-1 `postal_code` is an optional bounded text value; no country-specific normalization or validation rule is approved.
- Client-1 `category` is an optional bounded text label; no category entity, hierarchy, fixed choice list, or lifecycle is approved.
- The maintained Customer detail profile may show only Leads, Interactions, and Sales already visible to the actor through their existing backend scopes.

### 5.2 CustomerPhone

Fields:

```text
customer
raw_phone
normalized_phone
label nullable
is_primary
is_active
created_at
updated_at
```

Rules:

- Normalize Iranian phone formats consistently.
- Prevent silent duplicate active customer identities for the same normalized phone.
- One active primary phone per Customer.
- Repeated opportunities create new Leads, not duplicate Customers.
- Shared household numbers, if required later, need an explicit conflict/override workflow.

### 5.3 Lead

Fields:

```text
customer
source nullable
campaign_or_batch nullable
interested_product nullable
status
assigned_to nullable
assigned_by nullable
assigned_at nullable
next_follow_up_at nullable
closed_at nullable
created_by
notes
source_payload JSON
created_at
updated_at
```

Rules:

- One Customer can have many Leads.
- `source_payload` is controlled source metadata, not a replacement for core columns.
- Status codes are backend-owned; the frontend only maps codes to Persian labels/colors.
- Initial Lead assignment method is **UNRESOLVED**. Do not implement round-robin/equal split/product/city/team/self-pick without approval.

Provisional status candidates, not confirmed contractual values:

```text
new
assigned
contacted
no_answer
follow_up
not_interested
invalid_number
won
lost
```

### 5.4 LeadAssignmentHistory

Fields:

```text
lead
from_user nullable
to_user
changed_by
reason nullable
changed_at
```

Rules:

- Append-oriented.
- Required for initial assignment/reassignment where applicable.
- Reassignment must update the Lead and create history/audit atomically.
- Historical assignment policy for retrospective KPI denominators is **UNRESOLVED**.

### 5.5 Interaction

Fields:

```text
lead
customer optional denormalized
agent
phone
direction
outcome
occurred_at
next_follow_up_at nullable
notes
created_at
updated_at
```

Rules:

- Manual entry in V1.
- Minimum confirmed information: agent/caller, phone number, result/outcome.
- If Customer is denormalized, it must equal `lead.customer`.
- Agent/ownership fields are server-controlled.

Direction codes:

```text
inbound
outbound
```

Provisional outcome candidates, not final contractual values:

```text
answered
no_answer
busy
invalid_number
call_back
not_interested
sale
```

Automatic duration, recording, telephony provider, start/end tracking, and call-center API are not confirmed.

### 5.6 Product

Fields:

```text
sku
name
current_price
description nullable
is_active
created_by
updated_by
created_at
updated_at
```

Rules:

- Read-only for Sales Agents.
- Elevated roles may create, edit, and deactivate.
- Historical sales use price snapshots and must not change when `current_price` changes.

### 5.7 Sale

Fields:

```text
lead
customer derivable/optional denormalized
sold_by
product nullable
quantity default 1
unit_price_snapshot nullable
total_amount
status
sold_at
notes
created_at
updated_at
```

Status codes:

```text
confirmed
cancelled
```

Rules:

- Sale is an operational success record, not a legal/accounting Invoice.
- `customer`, when stored, must equal `lead.customer`.
- `sold_by` is server-controlled and authorized for the Lead.
- Product and unit-price snapshot must be paired according to the implemented database rules.
- Quantity is positive.
- When unit price is present, total must equal unit price multiplied by quantity under the approved decimal/rounding rule.
- Manager-or-higher correction/cancellation is a dedicated audited service/action.
- Normal workflows do not hard-delete Sales.

### 5.7A SalesDocument and PostalStatusHistory

`SalesDocument` is the minimal Client-1 internal operational sales document. It is not an Order, quotation, legal/accounting Invoice, Payment, or ledger row. Sale remains the operational success record.

Fields: required Customer; optional Sale; unique bounded human-readable internal document number; immutable server-owned province, city, postal-code, and address snapshots; required bounded current postal status; registration actor/time; active flag; notes; timestamps.

Rules:

- A linked Sale must belong to the selected Customer. Registration copies the current Customer geography/address and later Customer edits do not rewrite it.
- Sales Manager, Company IT, and Platform Admin may register, deactivate, and transition postal state through atomic audited services. Sales Agent has read-only access only through its scoped Customer or own Sale relationship.
- PostalStatusHistory is append-only and stores prior status, new status, actor, reason, and time. No ordinary hard deletion or generic document update exists.
- Exact postal choices and allowed transition graph remain unresolved. Until approved, the system accepts a required bounded single-line explicit status, blocks blank/same-state transitions, and does not infer carrier, return, tracking, or cancellation meaning.
- Tax, payment, ledger, legal numbering, fiscal correction, PDF, carrier integration, and full Invoice remain outside this phase.

### 5.8 ActivityLog

Fields:

```text
actor
request_id nullable
action
object_type
object_id
safe_changes JSON
ip_address nullable
created_at
```

Rules:

- Sensitive actions are audited, including reassignment, role changes, Sale correction/cancellation, and future financial/shipping changes.
- Audit rows keep the request ID associated with the application/edge response.
- Never store passwords, password hashes, tokens, API keys, cookies, authorization headers, raw secrets, `.env` values, or unsafe serializer payloads.
- Proxy-derived IPs are trusted only under explicit trusted-proxy CIDR configuration.

### 5.9 Client-1 AfterSalesRequest

Approved additive boundary:

```text
customer required
sale nullable
operational_document nullable
subject
description
status
assigned_to nullable
created_by
closed_at nullable
created_at
updated_at
```

No exact status vocabulary or transition graph was supplied. Status therefore remains required bounded single-line text. Create, assignment, status change, and close use dedicated atomic services and append-only history. Close is final until reopen semantics are approved. Sales Manager, Company IT, and Platform Admin manage company cases. Only an active clean Sales Agent in `after_sales` may be assigned and may view/change status on assigned cases. It gets no unrelated Customer, Lead, Interaction, Product, Sale, operational-document, or report scope.

---

## 6. Relationship contract

```text
User 1 -> N Customer(created_by)
User 1 -> N Lead(created_by)
User 1 -> N Lead(assigned_to)
User 1 -> N Lead(assigned_by)
Customer 1 -> N CustomerPhone
Customer 1 -> N Lead
Product 1 -> N Lead(interested_product, optional)
Lead 1 -> N LeadAssignmentHistory
User 1 -> N LeadAssignmentHistory(from_user/to_user/changed_by)
Lead 1 -> N Interaction
User 1 -> N Interaction(agent)
Lead 1 -> 0..N Sale
User 1 -> N Sale(sold_by)
Product 1 -> N Sale(product, optional)
Customer 1 -> N SalesDocument
Sale 0..1 -> N SalesDocument
User 1 -> N SalesDocument(registered_by)
SalesDocument 1 -> N PostalStatusHistory
User 1 -> N PostalStatusHistory(changed_by)
Customer 1 -> N AfterSalesRequest
Sale 0..1 -> N AfterSalesRequest
SalesDocument 0..1 -> N AfterSalesRequest
AfterSalesRequest 1 -> N AfterSalesHistory
User 1 -> N ActivityLog(actor)
```

Use database constraints and transactional services to protect cross-field consistency.

---

## 7. Workflow contract

### 7.1 Customer and Lead

- V1 operational entry is manual.
- Normalize phones before duplicate lookup/creation.
- A repeated person/phone in another campaign/month/product becomes a new Lead attached to the existing Customer in normal cases.
- Do not silently create a duplicate Customer when the normalized active phone already belongs to another Customer.

### 7.2 Lead assignment and reassignment

- Initial assignment method: **UNRESOLVED**.
- Reassignment: confirmed for Sales Manager, Company IT, and Platform Admin.
- Reassignment is performed through a dedicated service/action, not unrestricted `assigned_to` PATCH.
- It must update assignment fields, append `LeadAssignmentHistory`, and append safe audit data atomically.

### 7.3 Interaction entry

- Sales Agent may register an Interaction only for an assigned permitted Lead.
- Elevated roles may operate across permitted company scope.
- Follow-up information may update the Lead through a defined service if implemented; avoid hidden serializer side effects.

### 7.4 Sale entry

- Sales Agent marks successful Sale for an assigned permitted Lead.
- Sale creation snapshots quantity/price/amount and creates audit evidence as required.
- Full Invoice creation is not part of the confirmed Sales Agent workflow.

### 7.4A Internal document and postal transition

- Elevated roles register a SalesDocument from a scoped Customer and optional same-Customer Sale.
- Registration atomically creates the document, immutable location/address snapshot, first postal-history row, and safe audit row.
- Elevated roles change current postal status only through the dedicated service; each successful change appends history and audit in the same transaction.
- Sales Agent access is read-only and derives only from the existing Customer/Sale selector scope.

### 7.5 Deletion policy

- Users, Customers, Products, Leads, Sales, and support records are normally deactivated/cancelled rather than physically deleted.
- Interactions, assignment history, Sales, and audit records are append-oriented.
- Hard deletion is restricted to explicit platform-maintenance procedures.

---

## 8. API conventions

### 8.1 Base style

- Versioned REST API under `/api/v1/`.
- JSON for normal APIs and XLSX for approved exports.
- Same-origin session/CSRF by default.
- Consistent pagination, filtering, ordering, errors, and request IDs.
- OpenAPI generated and validated.

### 8.2 Candidate endpoints

```text
POST /api/v1/auth/login/
POST /api/v1/auth/logout/
GET  /api/v1/auth/me/

/api/v1/users/
/api/v1/customers/
/api/v1/customer-phones/
/api/v1/leads/
POST /api/v1/leads/{id}/reassign/
/api/v1/interactions/
/api/v1/products/
/api/v1/sales/
/api/v1/sales-documents/
/api/v1/sales-documents/{id}/transition-postal-status/
/api/v1/sales-documents/{id}/postal-history/
/api/v1/after-sales/
/api/v1/after-sales/{id}/assign/
/api/v1/after-sales/{id}/transition-status/
/api/v1/after-sales/{id}/close/
/api/v1/after-sales/{id}/history/
/api/v1/reports/user-performance/
/api/v1/reports/sales-documents/
/api/v1/exports/user-performance.xlsx
```

Exact router naming may follow the established project conventions, but behavior and authorization must remain consistent.

### 8.3 Error contract

Errors must:

- use stable machine-readable codes;
- provide safe field/non-field details;
- include the request ID in the response/header contract;
- avoid stack traces, secrets, internal paths, SQL, and sensitive payloads in production;
- use correct HTTP statuses for authentication, permission, validation, conflict, not found, throttling, and server errors.

---

## 9. Validation and integrity rules

At minimum:

- normalize and validate Iranian phone numbers consistently;
- enforce active normalized-phone uniqueness strategy;
- enforce one active primary phone per Customer;
- prevent cross-customer phone mutation through nested endpoints;
- protect Customer/Lead/Sale denormalized consistency;
- positive Product prices, Sale quantity, and amounts as applicable;
- Sale product/price pairing and total arithmetic at service and database level where supported;
- dedicated transitions for reassignment, Sale correction/cancellation, role change, and deactivation;
- transactional writes for multi-record invariants;
- deterministic timezone-aware timestamps;
- server-controlled ownership/role/audit fields;
- no mass assignment of privilege fields.

Exact final Lead statuses, Interaction outcomes, decimal/rounding behavior, and certain report semantics must come from approved source documents or remain explicitly provisional.

---

## 10. Reporting and XLSX contract

### 10.1 Confirmed high-level requirement

- Reports are visible inside Kariz CRM.
- The same approved filtered result can be exported to XLSX.
- V1 uses predefined reports, not a dynamic report builder.
- Client-1 includes a bounded dynamic report builder in `FINAL_WAVE_LOW`, but its allowlisted sources/fields/joins/aggregates, ownership/sharing, authorization, query/export limits, audit, and acceptance rules remain **BLOCKED**. It does not alter the current predefined-report contract.
- Authorization scope applies identically to JSON and XLSX.

### 10.2 Unambiguous metrics that may proceed when stronger rules are absent

Use exact names that state their semantics:

```text
customers_created_count
sales_count
sales_amount
average_sale_amount
```

Definitions:

- `customers_created_count`: Customers created by the selected user in the selected period.
- `sales_count`: confirmed Sales in the selected period and permitted scope.
- `sales_amount`: sum of confirmed `Sale.total_amount` in the selected period and permitted scope.
- `average_sale_amount`: `sales_amount / sales_count`; return zero when `sales_count` is zero.

Clearly named interaction/call counts may be added only when the qualifying outcome set is explicit.

### 10.3 Unresolved metrics

Do not publish misleading generic metrics until approved:

- generic “number of customers” semantics;
- unique customers handled;
- leads-assigned denominator across reassignment history;
- conversion rate denominator and reassignment policy;
- final answered/qualifying call outcome grouping.

Implement the unambiguous report foundation, filters, role scoping, XLSX, OpenAPI, and deterministic tests while recording unresolved metrics in `KARIZ_PROJECT_HANDOFF.md`.

### 10.4 Candidate filters

```text
date range
user
team
lead status
interaction/call outcome
product
campaign/batch
```

Only expose filters supported by actual fields and approved authorization.

---

## 11. Audit, logging, and request tracing

- Generate or preserve one request ID for every application/edge response.
- Bind the same request ID to audit rows created during the request.
- Return the request ID using the established response-header/body contract.
- Trust forwarded IP/proto headers only from configured trusted proxies/CIDRs.
- Exclude secrets and sensitive fields from application, proxy, audit, and exception logs.
- Configure production log rotation and avoid unbounded disk growth.

---

## 12. Production and deployment requirements

Minimum runtime artifacts:

```text
Dockerfile
compose.yaml or docker-compose.yml
Nginx configuration
PostgreSQL persistent volume
.env.example without real secrets
documented start/stop/build/migrate/admin commands
application/database health checks
restart policies
log rotation
```

Production configuration must include:

- DEBUG disabled;
- environment-only secret key/database credentials;
- explicit allowed hosts and trusted CSRF origins;
- secure session/CSRF cookies and HTTPS/proxy settings for the real deployment;
- static file handling;
- approved WSGI/ASGI server;
- least-privilege containers/users where practical;
- dependency pinning/reproducible build strategy;
- database-aware readiness/health checks;
- documented migration and rollback procedure.

### 12.1 Backup and restore

Required before responsible handover:

- automated daily PostgreSQL backup;
- storage outside the database container, preferably separate disk/NAS;
- configurable retention, including daily/weekly policy;
- at least one real restore test into a disposable database;
- recovery runbook;
- log rotation.

Backup destination and retention duration remain **UNRESOLVED** and require deployment-owner input, but scripts/configuration/runbook work should continue.

### 12.2 TLS

A real hostname/certificate path is required for final TLS proof. The repository must still contain secure TLS-ready Nginx/production guidance without embedding certificates or keys.

---

## 13. Test requirements

Critical automated coverage includes:

- object-level queryset scoping for every role;
- direct-ID and query/filter data-leak attempts;
- privilege escalation through role/admin fields;
- inactive-user access;
- phone normalization, duplicates, primary-phone, inactive-phone, cross-customer, and rollback behavior;
- reassignment history and audit;
- Sales Agent product-mutation rejection;
- Interaction and Sale ownership rules;
- Sale price snapshot and database integrity constraints;
- Sale correction/cancellation authorization and audit;
- request-ID propagation and audit binding;
- trusted/untrusted proxy IP behavior;
- report formulas with zero denominators;
- report authorization and filters;
- XLSX filter parity and valid workbook generation;
- database-aware health checks;
- migrations and no schema drift;
- OpenAPI schema validation;
- production deploy checks with safe test environment values.

Use deterministic factories/fixtures and avoid real personal data.

---

## 14. Frontend contract and branding boundaries

- Template/demo files provide visible form/table/action evidence only.
- Many original scripts simulate success and are not real API integrations.
- Build small Kariz-specific API/page modules rather than connecting every demo script.
- Active product branding is `Kariz CRM` / `کاریز`.
- Replace user-visible Metronic/KeenThemes branding, titles, login/footer text, and vendor/demo links.
- Do not blindly rename runtime identifiers such as `KTMenu`, `KTDrawer`, `KTUtil`, `data-kt-*`, or vendor API names when behavior depends on them.
- Preserve legally required third-party notices outside user-visible product branding.
- Active UI is Persian-only unless a newer requirement enables multilingual support.

---

## 15. Open unresolved decisions

Keep these explicit and do not silently convert them into confirmed rules:

1. Invoice/postal V1 decision: manager/IT manual entry, import, external API, or phase-two deferral.
2. Exact mandatory pages/modules for accepted V1.
3. Initial Lead assignment method.
4. Final Lead status list.
5. Final Interaction/call outcome list and qualifying call groupings.
6. Exact “number of customers” KPI semantics.
7. Conversion-rate denominator and reassignment-history policy.
8. After-sales workflow, statuses, and Invoice requirement.
9. Inbound SMS source/workflow.
10. UI/XLSX calendar/timezone/Jalali presentation rule.
11. Exact XLSX columns and formatting.
12. Server resources and concurrent-user target.
13. Backup destination and retention.
14. External website data direction, credentials, and network path.
15. Production hostname/certificate/TLS path.
16. **RESOLVED 2026-08-11:** four fixed role codes and Persian labels are mapped in section 4; Platform Admin custody stays with `platform_admin`, and `company_it` cannot grant or manage it. Team/workstream scope remains a separate open decision.
17. **RESOLVED 2026-08-12 for Client-1:** no Team model; Sales Manager has company-wide business scope and may administer Sales Agent accounts only. Elevated-role direct IDs are masked and role grants remain denied. A future multi-team product still needs a separate decision.
17. No-seat-cap meaning, total accounts, peak concurrency, capacity target, and load abort rule.
18. Customer category/postal/address/history/export/bulk/360 contracts.
19. Lead conversion/priority/archive/Opportunity/Pipeline contracts.
20. Calendar/task/project/reminder/notification/manual specialist-call contracts.
21. Product category, Inventory/stock/cost/multi-price/discount/profit contracts.
22. Order/internal document/quotation/accounting Invoice/Payment/ledger/cheque/installment/customer-account contracts.
23. Detailed/domain/P&L/receivable/PDF/dynamic-report formulas, sources, visibility, and examples.
24. File storage/scanner/version/retention/download/backup policy.
25. Global search/saved-filter/XLSX-import contracts.
26. Automation/dynamic-permission/PWA/anomaly-detection contracts.
27. Per external website/store/gateway/accounting/email/SMS/telephony integration direction, official documentation, security, idempotency, reconciliation, and owner.
28. One all-capability release versus approved staged delivery, plus ordering among unmarked additions; explicitly low-priority additions remain last.

Unresolved decisions block only the affected behavior. Continue all independent implementation and release-readiness work.

---

## 16. Definition of done

The backend is not production-ready until evidence shows:

- approved scope implemented through schema, services, APIs, authorization, tests, and OpenAPI;
- all role/object isolation acceptance tests pass;
- migrations apply and no drift exists;
- PostgreSQL production-like migration/boot evidence exists;
- Docker Compose and Nginx production-like stack boots and passes health/static/API smoke tests;
- secure production settings pass deployment checks;
- backup runs and restore is proven;
- logging/request IDs/health/readiness are operational;
- no secrets or forbidden artifacts are tracked/shipped;
- no open P0/P1 repository-controlled security/config/code defect remains;
- deployment, upgrade, rollback, backup, restore, and incident runbooks are complete;
- any remaining external/business blocker is explicit and prevents only the affected production claim.

When repository-controlled work is complete but hostname/certificate/server/credentials or unresolved business decisions remain, label the result **production candidate; external verification pending**, not fully production-ready.
