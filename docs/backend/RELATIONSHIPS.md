# Relationship catalog

- User 1:N Customer through required, server-controlled `created_by`; PROTECT; creator affects agent visibility; indexed.
- Customer 1:N CustomerPhone through required owner; PROTECT; phone does not own customer; one active primary per Customer, global active normalized identity, and ASCII `+98[1-9][0-9]{9}` shape constraints apply.
- User 1:N Lead through required `created_by`; PROTECT; server-controlled; creator alone does not grant agent visibility after assignment.
- User 1:N Lead through nullable `assigned_to` and `assigned_by`; PROTECT; server-controlled; assignee controls Sales Agent visibility; indexed. Assignee, assigner, and assignment time are all set or all empty.
- Customer 1:N Lead through required customer; PROTECT; historical leads prevent customer deletion.
- ProductCategory 1:N Product through nullable category; PROTECT; Product has zero or one Category. Active Category assignment is service-locked. A Category cannot deactivate while an active Product references it; inactive Products preserve historical links.
- Product 1:N Lead through nullable interested product; PROTECT; product deactivation preserves links.
- Lead 1:N LeadAssignmentHistory; PROTECT; append-only; history cannot own/delete lead.
- User 1:N LeadAssignmentHistory through nullable prior user and required target/actor; PROTECT; server-controlled.
- Lead 1:N Interaction; PROTECT; interaction is historical. User 1:N Interaction through required agent; PROTECT. Customer is required denormalized data and must equal `lead.customer`.
- Lead 1:N Sale; PROTECT. User 1:N Sale through required seller; PROTECT. Product 1:N Sale through nullable product; PROTECT. Customer is required denormalized data and must equal `lead.customer`.
- Customer 1:N SalesDocument; PROTECT. Sale 1:N SalesDocument through an optional link; PROTECT. The registration service requires a linked Sale to belong to the required Customer. User 1:N SalesDocument through required `registered_by`; PROTECT.
- SalesDocument 1:N PostalStatusHistory; PROTECT and append-only. User 1:N PostalStatusHistory through required `changed_by`; PROTECT.
- Customer 1:N AfterSalesRequest through required `customer`; PROTECT. Sale 1:N AfterSalesRequest and SalesDocument 1:N AfterSalesRequest through optional links; PROTECT. Creation locks all supplied rows and requires each optional link to belong to the required Customer.
- User 1:N AfterSalesRequest through nullable `assigned_to` and required `created_by`; PROTECT. Assignee must be an active clean `sales_agent` in the bounded `after_sales` workstream. User 1:N AfterSalesHistory through actor and nullable prior/new assignee; PROTECT. AfterSalesRequest 1:N AfterSalesHistory; PROTECT and append-only.
- User 1:N ActivityLog through nullable actor; PROTECT; append-only. Null permits retained system events only. `actor_role_snapshot` and account-target `object_role_snapshot` are stored role-at-action values, not extra foreign keys; append-only application flow prevents later role changes from widening Company IT audit visibility.
- Customer 1:N InboundSMS through nullable `customer`; PROTECT. The internal ingest service links Customer only when the normalized inbound sender matches exactly one active CustomerPhone. Lead 1:N InboundSMS through nullable `lead`; PROTECT. Lead is linked only when that resolved Customer currently has exactly one Lead; otherwise Customer may remain linked while Lead stays null. Neither relation is guessed or widened by an operator query.

User foreign keys can structurally point at any User row, but CRM services/selectors exclude every row with a staff/superuser flag, group membership, or direct permission. Actors and assignment targets must also be active; approved reports may retain otherwise-clean inactive accounts for historical rows. The gate applies to login/routes, user administration, assignment targets, and report users. No ordinary API can cascade-delete historical rows. User and business foreign keys use `PROTECT`.
