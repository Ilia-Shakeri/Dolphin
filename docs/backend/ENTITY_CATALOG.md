# Entity catalog

## User

Authenticated CRM account. Extends Django's abstract user with nullable phone, fixed `role`, and timestamps. Username and password behavior follow Django, including configured password validators. Role defaults to `sales_agent`; a database check permits only the four fixed role codes; inactive users cannot use APIs. CRM role is separate from staff, superuser, groups, and permissions. Role is server-controlled. Ordinary deletion is not exposed. Creation, profile/password/account changes, and role changes are safely audited without password values.

## Customer

Stable contact identity. Fields: full name, optional national ID/email/province/city/address, notes, creator, active flag, timestamps. Creator is server-controlled and indexed. National ID is indexed but not unique because policy is absent. Normal flow deactivates. Customer deletion is not exposed. Deactivation is audited.

## CustomerPhone

Phone identity owned by one customer. Fields: customer, raw phone, normalized phone, optional label, primary/active flags, timestamps. Normalized value is server-produced and indexed. Active normalized value is unique within one customer. At most one active primary phone exists per customer. Inactive duplicates and the same number on another customer are permitted. Shared-number policy is unresolved, so no global uniqueness exists. Deletion is not exposed.

## Lead

Sales opportunity for one customer. Fields: customer; optional source, campaign/batch, product, status, assignee, assigner, assignment time, next follow-up and close time; creator; notes; controlled source payload; timestamps. Ownership fields are server-controlled and indexed. A database check requires assignee, assigner, and assignment time to be either all set or all empty. Status has no inferred enum. Deletion and unrestricted assignment are not exposed.

## LeadAssignmentHistory

Append-only ownership change. Fields: lead, optional prior user, target user, actor, optional reason, time. Created only by assignment services. Indexed by lead/time and target/time. No mutation endpoint.

## Interaction

Manual contact record. Fields: lead, denormalized customer, agent, phone, optional direction/outcome, occurrence time, optional next follow-up, notes, timestamps. Customer and agent are server-controlled and checked against the lead and actor. Outcome choices wait for authority. The API is append-only: no update or deletion endpoint.

## Product

Sellable reference. Fields: unique SKU, name, current decimal price, optional description, active flag, creator/updater, timestamps. Money is non-negative in validation and the database. Creator/updater are server-controlled. Normal flow deactivates. Product changes are manager/admin-only, locked, and audited.

## Sale

Operational sale, not invoice. Fields: lead, denormalized customer, seller, optional product, positive quantity, optional unit-price snapshot, total amount, fixed status (`confirmed`, `cancelled`), sale time, notes, timestamps. Ownership and snapshots are server-controlled. Product and unit-price snapshot are both present or both absent. Product sales require total amount to equal snapshot price times quantity. Amounts are non-negative. Creation/cancellation use atomic services. Cancellation is audited. No deletion endpoint.

## ActivityLog

Append-only sensitive action log. Fields: optional actor, operation, object type/id, safe changes JSON, optional request ID/IP, creation time. Indexed by time and object. No API mutation. The service accepts only named safe keys with strict value shapes; unknown keys and unsafe values are dropped. Work done inside an HTTP request stores the response request ID. The direct peer IP is stored unless that peer belongs to an explicitly trusted proxy CIDR, in which case a valid `X-Real-IP` value is used.
