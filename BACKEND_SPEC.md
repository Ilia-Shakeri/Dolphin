# ForooshBin — Backend Specification

**Document status:** Provisional authoritative implementation specification assembled from the established ForooshBin conversation context and confirmed decisions. Newer explicit user decisions override this document. **Disposition (P0 audit 2026-08-14, corrected P0R 2026-08-14): KEEP_AND_REWRITE.** This document remains the normative business/backend contract; live status, evidence, and the single decision register live only in `KARIZ_PROJECT_HANDOFF.md`. Section 15 below no longer duplicates that register. P0 corrected §2.3/§2.4 (stale postal/SMS blocked-module claims contradicting this document's own §5.7A/§5.9 and the actual code). P0R corrected an over-expanded Client-1 scope claim (§2.6, now three explicit tiers), an incorrect Sales Manager user-administration rule (§4/§4.1, `BIZ-005`), and an ambiguous "Linux target" architecture line — all verified by direct code inspection, not by re-reading old prose.

**Product:** ForooshBin / فروش‌بین
**Architecture:** Django + Django REST Framework + PostgreSQL + Docker Compose + Nginx, modular monolith. **Correction (P0R, 2026-08-14):** "Linux target" describes the *application container image* (Linux/amd64, per `Dockerfile`/`docs/ops/DEPENDENCIES.md`) — it is not a claim about the customer's physical hosting architecture. Whether the target host runs Linux directly, Windows Server with a Hyper-V/container layer, or a dedicated appliance is unresolved and depends on the infrastructure survey in `KARIZ_CLIENT1_CODEX_ROADMAP.md`'s early infrastructure-survey gate; see `KARIZ_PROJECT_HANDOFF.md` for the exact open questions.
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

ForooshBin is an internal sales and customer-operations CRM for companies that receive phone/SMS-originated leads, distribute work to sales agents, track manual calls/interactions and successful sales, monitor performance, and export predefined reports to XLSX.

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

`AfterSalesRequest` is implemented. It requires a Customer and may optionally reference a Sale and a `SalesDocument` (the internal operational document defined in §5.7A) — not an Invoice, which does not exist in this codebase. See §5.9 for the exact field/authorization contract.

### 2.4 Blocked implementation modules

Do not implement or claim completion for the following until a newer explicit decision defines source, creator, workflow, statuses, permissions, and acceptance criteria. Section 2.6 confirms that several families now belong to the Client-1 end target; target inclusion does not clear these implementation blocks:

- Full Invoice and InvoiceItem module.
- Invoice count/amount by city or province (this requires the Invoice module above; it is distinct from the already-implemented `SalesDocument` province/city/postal-status report, see §5.7A).
- External SMS provider integration: the live adapter/webhook only. **Correction (P0 audit, 2026-08-14):** provider-neutral internal storage and reporting over inbound SMS is implemented (see §5's InboundSMS contract in `docs/backend/ENTITY_CATALOG.md` and `docs/backend/API_CONTRACT.md`); only the live provider adapter, webhook, and outbound SMS remain blocked pending the exact material listed in `docs/backend/SMS_PROVIDER_ADAPTER_REQUIREMENTS.md`.
- Automatic call-center/telephony integration.
- Ecommerce/order/shipping/payment/inventory/tax/return/refund modules.
- External website synchronization.

**Correction (P0 audit, 2026-08-14):** "Postal/shipping status and history" was removed from this list. The internal operational `SalesDocument`/`PostalStatusHistory` pair is implemented per §5.7A/§6/§7.4A of this same document and verified against the actual code; it was stale here since that feature shipped. It is not an accounting/legal Invoice and does not clear any Invoice-related block above.

**Note (P0 audit, 2026-08-14):** `ProductCategory` and `InboundSMS` are implemented entities that were added after this document's §5 was last extended. Their field/authorization contracts are maintained only in `docs/backend/ENTITY_CATALOG.md`, `docs/backend/RELATIONSHIPS.md`, and `docs/backend/API_CONTRACT.md` to avoid a second drift-prone copy; this document's business-rule authority (this section, §4, §9) still applies to them.

**Correction (direct product-owner decision, 2026-08-16).** The first two entries of §2.4 above — "Full Invoice and InvoiceItem module" and the inventory/order/payment part of the ecommerce line — are **no longer blocked and are now implemented.** The product owner directed that, rather than stopping on unresolved non-critical business detail, the codebase implement conservative, bounded, per-deployment-configurable semantics and document every choice. That decision outranks the earlier block, and this paragraph records the change instead of leaving the two statements to contradict the code.

What that authorised, and what it did **not**:

- **Built:** `inventory` (warehouse, stock level, append-only movement ledger, moving weighted-average purchase cost) and `billing` (Quotation, Order, Invoice/InvoiceItem, Payment, allocation, cheque, installment plan, append-only customer ledger), with receivables, gross-profit, and stock-valuation reports, and browser print/PDF for invoice and quotation. Semantics: `docs/backend/INVENTORY_SEMANTICS.md`, `docs/backend/BILLING_SEMANTICS.md`.
- **Still blocked, unchanged:** live SMS provider adapter/webhook and outbound SMS; telephony/call-centre integration; external website/store synchronisation; payment gateway; accounting-software integration. Each still needs the exact provider material named in §2.4.
- **Deliberately not invented:** this code claims **no tax, accounting, or legal compliance for any jurisdiction**. Tax is off by default and is a single configurable percentage over one taxable base; multi-rate tax, exemptions, withholding, credit notes as a distinct document, interest, and penalties are absent rather than approximated. The §2.6 non-invention guard below therefore still stands in full for everything not listed as built above: no mandatory Invoice source, no mandatory conversion step, no mandatory inventory reservation, no mandatory Payment→Invoice allocation (payment on account is supported), and no accounting basis is asserted.

### 2.5 Out of scope by default

- Public multi-tenant SaaS.
- Microservices, Kubernetes, Redis/Celery, or complex cloud infrastructure without a concrete requirement.
- A company-facing dynamic role/permission designer.
- Implementation of all template demos/plugins/pages.
- 24/7 support or unlimited free maintenance.

**Correction (P0R audit, 2026-08-14):** the two lines below previously claimed dynamic role/permission design and dynamic report building were "confirmed" Client-1 target inclusions. That was an over-expansion of scope not backed by a direct product-owner decision. Per §2.6's Tier C, both stay out of scope by default and are not required Client-1 deliverables unless a newer direct decision explicitly approves them.

### 2.6 Client-1 scope — three tiers (corrected P0R, 2026-08-14)

**Correction (P0R audit, 2026-08-14):** this section previously stated that "every named capability family must exist in the end target" as a blanket `CONFIRMED` claim. That was an over-expansion not backed by a direct product-owner decision — it treated candidate/backlog ideas the same as approved requirements. It is replaced by three explicit tiers. This tiering is itself a direct product-owner decision and is authoritative over any earlier prose in this document or in Git history.

**Tier A — implemented baseline.** Proven by current models, migrations, services, APIs, maintained UI, and tests (verified against actual code, not claimed from templates): authentication/sessions/own profile; fixed application roles and backend object scope; users; customers and phone numbers; leads, assignment, and assignment history; interactions and follow-up; `ProductCategory` and `Product`; operational `Sale`; internal `SalesDocument` and postal history/report; `AfterSalesRequest`; provider-neutral internal `InboundSMS` storage/reporting; current performance dashboard and XLSX; `ActivityLog`; versioned API, OpenAPI, health, and current security controls.

**Tier B — confirmed Client-1 target.** **Status update (2026-08-16):** most of this tier is now implemented under the direct decision recorded in §2.4 — warehouse and inventory, stock movement, purchase cost, pricing/discount/profit semantics, Order and Quotation, Invoice and InvoiceItem, numbering/rounding/correction/cancellation, Payment, cheque, installment, customer ledger, receivables, profit reporting, and operational printing. What remains unimplemented in this tier is: secure operational files/documents, and the approved external website/store/payment/accounting integrations. The original list is kept below unchanged for traceability of what the tier contained: warehouse and inventory; stock movement; purchase cost; approved pricing/discount/profit semantics; Order and Quotation (lifecycle to be approved); accounting/legal Invoice and InvoiceItem; approved tax/numbering/rounding/correction/cancellation rules; Payment; cheque; installment; Customer Account/Ledger; receivables; approved profit/loss reporting; operational PDF and printing (expected for the first operational delivery, but blocked until the exact document meaning and a redacted approved example exist); secure operational files/documents; approved external website/store/payment/accounting integrations, only after exact providers and official documentation exist.

**Tier C — candidate or low-priority backlog.** Not confirmed Client-1 delivery requirements unless a newer direct decision explicitly approves them: dynamic role/permission designer; complete Opportunity/Pipeline; general workflow-automation engine; installable PWA; abnormal-activity detection; full Task/Project/Meeting suite; global cross-module search; saved filters; bulk XLSX import; dynamic report builder beyond specifically approved reports; every Metronic/vendor demo page; avatar/notification/session-management extensions; every communication provider beyond the one already contracted (SMS); arbitrary other template functionality. These remain possible future product capabilities, not acceptance requirements.

`FINAL_WAVE_LOW` (used in older prose/Git history for the Tier-B financial/inventory/file families) meant "required but last in implementation order," not optional. It is superseded by Tier B above; do not reintroduce it as a separate label.

All new entities, statuses, transitions, formulas, role/workstream rules, report units, provider adapters, integration directions, storage policies, migrations, routes, and acceptance criteria remain **UNRESOLVED/BLOCKED** until the exact decisions recorded in `KARIZ_PROJECT_HANDOFF.md` are approved. No model, endpoint, UI route, or authorization change is authorized by tier membership alone — Tier B membership means "must eventually be decided and built," not "already approved to implement."

**Explicit non-invention guard (P0R, 2026-08-14):** being technically conventional is not the same as being approved. Do not invent or silently approve any of the following merely because they are common ERP/accounting patterns: the exact source of an Invoice (whether it may be created directly from a Customer, only from a Sale, only from an Order/Quotation, or several ways); a mandatory Order→Invoice or Quotation→Order conversion step; mandatory Inventory reservation on Order/Quotation; a mandatory Payment→Invoice allocation model (payment-on-account without an Invoice must remain a considered option, not excluded by default); the accounting basis for profit/loss (cash versus accrual, cost source); tax rules of any kind; or ledger debit/credit sign conventions. `KARIZ_CLIENT1_CODEX_ROADMAP.md` §7.4 lists several possible workflow shapes as non-exhaustive examples only — none of them is an approval.

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

- `sales_agent`: `بازاریاب (کال سنتر)`; a User and never a Customer; every marketer has an individual account; shared marketer accounts are prohibited.
- `sales_manager`: `مدیر فروشگاه`; the first client's store/sales manager; operational business data only, **no user-administration capability**.
- `company_it`: `مدیر فنی مشتری`; **disabled by default for Client 1** (see `PROFILE-001` / `DOC-COMPANY-IT-001` in `KARIZ_PROJECT_HANDOFF.md`); a future limited account requires a separate approved contract and must never grant, target, modify, or administer `platform_admin`.
- `platform_admin`: `مدیر پلتفرم`; reserved for the Kariz owner/developer team only; for Client 1 this is the **only** role permitted to create, edit, deactivate, or reactivate application users, and the only role permitted to change application role or operator workstream. Django Admin and server/database administration are not exposed to customer users under any role.

**Correction (product-owner decision, 2026-08-18): activation state is Platform Admin only.** Turning a customer or a product active/inactive is reserved for `platform_admin`. Operational roles keep every other write on those records. Deactivation continues to hide rather than delete: every order, invoice, payment and ledger row survives untouched, and reactivation restores the record.

**Correction (product-owner decision, 2026-08-18): a marketer's customer scope is own-entry.** `sales_agent` sees the customers they entered themselves. The previous rule also granted every customer behind a lead assigned to them. Consequence, accepted deliberately: an agent working an assigned lead can no longer open that lead's customer record.

**Correction (product-owner decision, 2026-08-18): campaign target audience.** A campaign is worked from a persistent list of identities (`sales.TargetAudienceMember`) carrying name, phone and status. Status is partly derived and not freely settable: an identity moves to `engaged` ("در تعامل") when the call centre records an interaction with it, and to `customer` ("مشتری") when the same normalized phone exists in the customer book; `customer` outranks `engaged`. Only `lead` and `failed` may be set by hand. Elevated roles edit the list; `sales_agent` reads the audience of campaigns assigned to them and writes nothing.

**Correction (product-owner decision, 2026-08-18): lead status vocabulary.** `Lead.status` is exactly `pending` / `completed` / `cancelled` (در انتظار تکمیل / تکمیل / کنسل شده). It was previously free text.

**Correction (product-owner decision, 2026-08-18): hand-recorded stock movements.** The movement write endpoint accepts exactly `opening`, `return_in` and `sale`. Other kinds remain in the model and are written by the operation that produces them (transfer, order issue), never typed in.

**Correction (product-owner decision, 2026-08-18): no role changes a password.** A password is set once, when the account is created. No interface offers to change one and the API refuses `password` on update, for every role including `platform_admin`. This removes an in-application credential-reset path entirely rather than restricting it. A forgotten password is recovered on the deployment host with `manage.py changepassword`, which needs server access rather than a session; the consequence — that account recovery now requires the operator, and that there is still no self-service reset (requirement 1.6 remains `BLOCKED_EXTERNAL` for want of an email/SMS provider) — is accepted deliberately.

Customer remains the actual store/customer/client contact and is displayed as `مشتری` / `مشتریان`. The `Customer` model, API path, database table, field names, fixed role codes, and stable internal identifiers remain unchanged.

**Correction (P0R audit, 2026-08-14 — `BIZ-005` resolved):** for the single-tenant Client-1 deployment, Sales Manager scope is company-wide for *business* records only (Customer/Lead/Interaction/Product/Sale/report). It has **no** user-administration capability: it may not list, create, edit, deactivate, reactivate, reset the password of, or change the workstream of any account, including Sales Agent accounts. This replaces the prior statement that Sales Manager could administer Sales Agent accounts, which is no longer an active rule (kept only as historical provenance in §15). No Team model is created. Client-1 uses a bounded `sales` / `after_sales` workstream on Sales Agent accounts only, settable only by Platform Admin; it does not add a fifth role or dynamic permission builder. Elevated roles must remain in `sales`. Seat/capacity remains a separate unresolved decision.

**Status (P1.7, 2026-08-15): implemented — no gap remains.** `users.manage_agents`
and `users.manage_non_platform` were removed from `accounts/access.py`, so
`sales_manager`, `company_it`, and `sales_agent` hold no `users.manage_*`
capability. `IsUserReader` therefore denies them the whole `/api/v1/users/`
surface, and `common/ui_views.py` hides the navigation entry and returns 403 on
the user pages. `accounts/services.py` `USER_ADMINS` is now
`{User.Role.PLATFORM_ADMIN}`, which makes the service layer authoritative for
every caller including management commands, and `UserViewSet._require_admin`
matches. This is the secure default of the shared codebase, not a Client-1
branch. Regression coverage lives in
`accounts/tests/test_user_administration_policy.py`.

A future deployment may reintroduce a narrower, explicitly-approved capability
only through the signed deployment manifest (`PROFILE-001`, Option C). Nothing
else may re-grant it.

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
| Manage ordinary users (create/edit/deactivate/reactivate) | No | **No** | **No** | Yes, every clean CRM identity |
| Change an existing user's password | No | No | No | **No — not exposed to any role** |
| Change role or operational workstream | No | **No** | **No** | Yes |
| Assign CRM roles | No | No | No | Yes |
| Grant platform admin/superuser | No | No | No | Yes |
| View audit log | No | No | Non-platform-safe audit; role disabled by default for Client 1 | All CRM audit |
| Django admin/server operations | No | No | No by default | Separately controlled, not exposed to customer users |

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

- Reports are visible inside ForooshBin.
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
- Active product branding is `ForooshBin` / `فروش‌بین`.
- Replace user-visible Metronic/KeenThemes branding, titles, login/footer text, and vendor/demo links.
- Do not blindly rename runtime identifiers such as `KTMenu`, `KTDrawer`, `KTUtil`, `data-kt-*`, or vendor API names when behavior depends on them.
- Preserve legally required third-party notices outside user-visible product branding.
- Active UI is Persian-only unless a newer requirement enables multilingual support.

---

## 15. Open unresolved decisions

**Correction (P0 audit, 2026-08-14):** this section previously duplicated a numbered decision list (with a numbering bug — two items both labeled "17") that drifts out of sync with the live register. There is now exactly one live, numbered register of open decisions: `KARIZ_PROJECT_HANDOFF.md` §14. This document does not maintain a second copy.

Two decisions affecting this document's own rules are resolved and stay recorded here as provenance:

- **RESOLVED 2026-08-11:** four fixed role codes and Persian labels are mapped in §4; Platform Admin custody stays with `platform_admin`, and `company_it` cannot grant or manage it. Team/workstream scope was a separate decision, resolved next.
- **RESOLVED 2026-08-12 for Client-1, superseded 2026-08-14 (`BIZ-005`):** no Team model; Sales Manager has company-wide *business* scope. The 2026-08-12 statement that Sales Manager "may administer Sales Agent accounts only" is no longer an active rule — kept here only as historical provenance. The current active rule is in §4: Sales Manager has no user-administration capability for Client 1. Elevated-role direct IDs are masked and role grants remain denied. A future multi-team product still needs a separate decision.

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
