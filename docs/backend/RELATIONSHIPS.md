# Relationship catalog

- User 1:N Customer through required, server-controlled `created_by`; PROTECT; creator affects agent visibility; indexed.
- Customer 1:N CustomerPhone through required owner; PROTECT; phone does not own customer; active primary and per-customer normalized constraints apply.
- User 1:N Lead through required `created_by`; PROTECT; server-controlled; creator alone does not grant agent visibility after assignment.
- User 1:N Lead through nullable `assigned_to` and `assigned_by`; PROTECT; server-controlled; assignee controls Sales Agent visibility; indexed. Assignee, assigner, and assignment time are all set or all empty.
- Customer 1:N Lead through required customer; PROTECT; historical leads prevent customer deletion.
- Product 1:N Lead through nullable interested product; PROTECT; product deactivation preserves links.
- Lead 1:N LeadAssignmentHistory; PROTECT; append-only; history cannot own/delete lead.
- User 1:N LeadAssignmentHistory through nullable prior user and required target/actor; PROTECT; server-controlled.
- Lead 1:N Interaction; PROTECT; interaction is historical. User 1:N Interaction through required agent; PROTECT. Customer is required denormalized data and must equal `lead.customer`.
- Lead 1:N Sale; PROTECT. User 1:N Sale through required seller; PROTECT. Product 1:N Sale through nullable product; PROTECT. Customer is required denormalized data and must equal `lead.customer`.
- User 1:N ActivityLog through nullable actor; PROTECT; append-only. Null permits retained system events only.

No ordinary API can cascade-delete historical rows. User and business foreign keys use `PROTECT`.
