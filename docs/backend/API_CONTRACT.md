# API contract

Base path: `/api/v1/`. Authentication: Django session cookie plus CSRF. Unsafe requests require CSRF outside test clients. Unauthenticated requests return 403 under DRF session authentication. Validation errors use DRF field errors. Every application response has `X-Request-ID`, including HTTPS redirects. The bundled Nginx edge makes its own ID for every response, forwards it to Django, and hides the duplicate upstream header. Direct application requests keep a caller value only when it uses 1-64 letters, digits, dots, underscores, or hyphens; otherwise Django makes a new value. The ID is for tracing, not authority. Audited request work stores the same ID.

## Authentication

- `POST auth/login/`: username and password; creates session. Inactive/invalid login is rejected. Application and Nginx rate limits protect repeated attempts.
- `POST auth/logout/`: authenticated; clears session.
- `GET/PATCH auth/me/`: current safe profile. Patch permits first name, last name, phone, and email only; it locks and safely audits changed field names.

## Users

- `GET/POST users/`, `GET/PATCH users/{id}/`: Company IT or Platform Admin. Sales Manager may read users but not administer them. New and reset passwords pass Django password validators.
- `POST users/{id}/change-role/`: Company IT can grant through `company_it`; Platform Admin can grant any fixed CRM role. Staff/superuser/groups/permissions are never writable.

## Customers and phones

- `customers/`: scoped list/create/retrieve/update. Create accepts optional nested `phone`. No DELETE.
- `POST customers/{id}/deactivate/`: owner or elevated operational role.
- `customer-phones/`: scoped list/create/retrieve/update. Customer ownership is checked. No DELETE.

## Leads and assignment

- `leads/`: scoped list/create/retrieve/update. Ownership/status fields are read-only. No DELETE.
- `POST leads/{id}/reassign/`: Sales Manager or Platform Admin; body has `to_user` and optional `reason`; atomic history and audit.

## Interactions, products, sales

- `interactions/`: scoped list/create/retrieve. Interaction records are append-only through the API. No update or DELETE.
- `products/`: authenticated read. Sales Manager or Platform Admin create/update.
- `POST products/{id}/deactivate/`: Sales Manager or Platform Admin.
- `sales/`: scoped list/create/retrieve. Creation snapshots product price and amount. No generic update/delete.
- `POST sales/{id}/cancel/`: Sales Manager or Platform Admin; optional reason; audited without raw reason text. The central cancel/correct service rejects correction until correction rules are approved.

## System and schema

- `GET health/live/`: public process liveness.
- `GET health/ready/`: public PostgreSQL readiness; 503 on database failure. `health/` remains a readiness compatibility route.
- `GET schema/`, `GET docs/`: OpenAPI document and UI for active authenticated users.

Reports, XLSX, status actions, audit browsing, and after-sales routes are deliberately absent pending authoritative rules.

Unknown request keys and server-controlled keys are rejected. Collection/detail update routes use PATCH, not PUT. Validation remains field-shaped under the standard DRF error convention. The bundled Nginx edge discards caller-supplied forwarding chains and sends its direct peer address to the application.
