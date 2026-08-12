# Entity catalog

The user-performance JSON and XLSX outputs are read-only projections over User, Customer, Product, and Sale. They add no persisted entity, relation, or migration.

## User

Authenticated CRM account. Extends Django's abstract user with nullable phone, fixed `role`, and timestamps. Username and password behavior follow Django, including configured password validators. Role defaults to `sales_agent`; a database check permits only the four fixed role codes. A login-capable CRM identity must be active, have one fixed CRM role, have both `is_staff` and `is_superuser` false, and have no Django group membership or direct permission. A row with any staff/superuser/group/direct-permission state is a server identity, not a CRM identity: it cannot use CRM login/routes and is excluded from user, report, and assignment querysets. An otherwise clean inactive CRM account cannot authenticate but remains visible to Company IT/Platform Admin account management for audited reactivation and to approved historical reporting. Inactive actors still fail every route and service gate. Role is server-controlled. Ordinary deletion is not exposed. Creation, profile/password/account changes, and role changes are safely audited without password values. Locked services return a conflict instead of demoting or deactivating the last active Platform Admin CRM identity. The terminal bootstrap is first-ever only and refuses any prior Platform Admin row, active or inactive.

## Customer

Stable contact identity. Fields: full name, optional national ID/email/province/city/postal code/category/address, notes, creator, active flag, timestamps. Postal code is an opaque text value capped at 32 characters because no country-specific format is approved. Category is a plain text label capped at 100 characters because no category entity, hierarchy, fixed choices, or lifecycle is approved. Address is capped at 2,000 characters and notes at 4,000 in API validation, services, and the PostgreSQL column type. Creator is server-controlled and indexed. National ID is indexed but not unique because policy is absent. Normal flow deactivates. Customer deletion is not exposed. Deactivation is audited. The Customer API includes a read-only active primary-phone projection; related Lead, Interaction, and Sale reads reuse their existing actor scopes.

## CustomerPhone

Phone identity owned by one customer. Fields: customer, raw phone, normalized phone, optional label, primary/active flags, timestamps. The normalizer translates supported Persian/Arabic digits, rejects other Unicode or unexpected characters, and stores only the ASCII shape `+98[1-9][0-9]{9}`. The normalized value is server-produced and indexed. Migration `sales.0008_customer_phone_normalized_shape` first aborts with bounded row IDs if stored data has another shape, then adds the database check. An active normalized value is globally unique so one active phone identity cannot silently create multiple Customers. At most one active primary phone exists per Customer. Inactive duplicates are permitted only when they still satisfy the normalized shape. A future shared-number workflow needs explicit conflict approval. Deletion is not exposed.

## Lead

Sales opportunity for one customer. Fields: customer; optional source, campaign/batch, product, status, assignee, assigner, assignment time, next follow-up and close time; creator; notes; controlled source payload; timestamps. Notes are capped at 4,000 characters. Ownership fields are server-controlled and indexed. A database check requires assignee, assigner, and assignment time to be either all set or all empty. Status has no inferred enum. Deletion and unrestricted assignment are not exposed.

## LeadAssignmentHistory

Append-only ownership change. Fields: lead, optional prior user, target user, actor, optional reason, time. Created only by assignment services. Indexed by lead/time and target/time. No mutation endpoint.

## Interaction

Manual contact record. Fields: lead, denormalized customer, agent, phone, required direction, required outcome, occurrence time, optional next follow-up, notes, timestamps. Direction is exactly `inbound` or `outbound`. Outcome is nonblank and capped at 80 characters; final outcome codes wait for authority. Notes are capped at 4,000 characters. Customer and agent are server-controlled and checked against the lead and actor. Migration `sales.0010_interaction_contract` rejects invalid legacy row IDs before adding database direction/outcome checks. The API is append-only: no update or deletion endpoint.

## Product

Sellable reference. Fields: unique SKU, name, current decimal price, optional description, active flag, creator/updater, timestamps. Description is capped at 4,000 characters. Current price is greater than zero in validation and the database. Creator/updater are server-controlled. Normal flow deactivates. Product changes are limited to Sales Manager, Company IT, and Platform Admin, locked, and audited.

## Sale

Operational sale, not invoice. Fields: lead, denormalized customer, seller, optional product, positive quantity, optional unit-price snapshot, total amount, fixed status (`confirmed`, `cancelled`), sale time, notes, timestamps. Notes are capped at 4,000 characters. Ownership and snapshots are server-controlled. Product and unit-price snapshot are both present or both absent. Product sales require total amount to equal snapshot price times quantity. Amounts are non-negative. Creation/cancellation use atomic services. Cancellation is audited. No deletion endpoint. Migration `sales.0009_bounded_free_text` reports only bounded offending row IDs before changing the six former unbounded text columns; it does not copy or rewrite their values.

## SalesDocument

Internal operational sales document, not an accounting/legal Invoice. Fields: required Customer, optional Sale, unique human-readable internal number, server-owned province/city/postal-code/address snapshots, current postal status, registration actor/time, active flag, notes, and timestamps. The registration service requires any linked Sale to belong to the selected Customer and copies geography/address from Customer once. Later Customer edits do not rewrite snapshots. Postal status is required bounded single-line text because exact Client-1 choices and transition graph remain unresolved. Registration, status transition, and deactivation are atomic elevated-role services with safe audit. No generic update or deletion endpoint.

## PostalStatusHistory

Append-only status evidence for one SalesDocument. Fields: prior status, new status, actor, optional reason, and time. Registration creates the first row with an empty prior value. Later rows are created only by the postal transition service. Foreign keys use PROTECT. No mutation endpoint exists.

## ActivityLog

Append-only sensitive action log. Fields: optional actor, actor-role snapshot, operation, object type/id, account-object role snapshot, safe changes JSON, optional request ID/IP, creation time. Role snapshots preserve role-at-action visibility even after a user changes role; role-change events explicitly keep the actor role and target's prior role. Indexed by time, object, and both snapshots. No API mutation. The service accepts only named safe keys with strict value shapes; unknown keys and unsafe values are dropped. Work done inside an HTTP request stores the response request ID. The direct peer IP is stored unless that peer belongs to an explicitly trusted proxy CIDR, in which case a valid `X-Real-IP` value is used. Platform Admin has read-only API access to all safe rows. Company IT scope uses snapshots, excludes Platform Admin actor/target and protected Platform Admin role-change activity, and hides legacy rows whose non-system actor or account target lacks the required snapshot. Other roles fail closed until a narrower Manager audit rule is approved.
