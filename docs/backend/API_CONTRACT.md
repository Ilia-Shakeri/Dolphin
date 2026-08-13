# API contract

Base path: `/api/v1/`. Authentication: Django session cookie plus CSRF. Unsafe requests require CSRF outside test clients. Normal API request and response bodies use JSON only; form, multipart, and HTML negotiation are rejected. The XLSX export is the sole approved binary response and still returns the shared JSON error envelope on failure. Unauthenticated requests return 403 under DRF session authentication. A valid CRM identity must be active, use one fixed CRM role, have no staff/superuser flag, and have no Django group or direct permission; server identities that fail this rule are rejected at login and every CRM permission gate. Validation errors keep field-shaped details and add `error.code` plus `error.request_id`. Stable codes include `validation_error`, `conflict`, `authentication_failed`, `permission_denied`, `not_found`, `not_acceptable`, `method_not_allowed`, `unsupported_media_type`, `parse_error`, `payload_too_large`, `throttled`, and `server_error`. True uniqueness or current-state clashes use HTTP 409 and `conflict`. Malformed JSON or JSON deeper than 32 container levels returns HTTP 400 `parse_error`. Request bodies are limited to 64 KiB at both the application and bundled edge; larger requests return HTTP 413 `payload_too_large`. An unhandled `/api/` fault returns safe JSON with HTTP 500, `server_error`, and the same request ID; exception text, stack, internal path, SQL, and payload are not returned. Every application response has `X-Request-ID`, including HTTPS redirects. The bundled Nginx edge redirects HTTP application traffic to its exact configured public HTTPS host, terminates only TLS 1.2/1.3 with externally mounted certificate files, sends fixed `X-Forwarded-Proto: https`, owns the edge request ID, and overwrites forwarding headers. Direct application requests keep a caller request ID only when it uses 1-64 letters, digits, dots, underscores, or hyphens; otherwise Django makes a new value. The ID is for tracing, not authority. Audited request work stores the same ID.

## Authentication

- `POST auth/login/`: username and password; creates session. Inactive/invalid credentials and any server identity with staff/superuser/group/direct-permission state are rejected without exposing which identity rule failed. Application and Nginx rate limits protect repeated attempts.
- `POST auth/logout/`: authenticated; clears session.
- `GET/PATCH auth/me/`: current safe profile. Patch permits first name, last name, phone, and email only; it locks and safely audits changed field names.

## Users

- `GET/POST users/`, `GET/PATCH users/{id}/`: Sales Manager lists and manages Sales Agent accounts only; Company IT manages clean non-platform accounts; Platform Admin manages every clean CRM identity. Inactive rows remain visible to their approved administrator for reactivation; staff/superuser/group/direct-permission identities remain hidden. New and reset passwords pass Django password validators. `workstream` is exactly `sales` or `after_sales`, is allowed as `after_sales` only for Sales Agent, and resets to `sales` on promotion.
- `POST users/{id}/change-role/`: Company IT can grant through `company_it`; Platform Admin can grant any fixed CRM role. Staff/superuser/groups/permissions are never writable. Demoting the last active Platform Admin CRM identity returns HTTP 409 `conflict`.
- `PATCH users/{id}/` with `is_active=false`: deactivating the last active Platform Admin CRM identity returns HTTP 409 `conflict`. A second active Platform Admin counts only when it also passes the CRM-identity guard.

## Customers and phones

- `customers/`: scoped list/create/retrieve/update. Existing payloads remain valid. Create accepts optional nested `phone`; responses add read-only `primary_phone`. Optional `postal_code` permits at most 32 characters and optional plain-text `category` permits at most 100. Address permits at most 2,000 characters; notes permit at most 4,000. Search also covers province, city, postal code, category, address, and normalized phone. No DELETE.
- `POST customers/{id}/deactivate/`: Sales Manager, Company IT, or Platform Admin. Sales Agents cannot deactivate Customers.
- `GET customers/{id}/leads/`, `GET customers/{id}/interactions/`, `GET customers/{id}/sales/`: paginated Customer-profile relations. The Customer ID is first masked through Customer scope, then each related queryset reuses the actor's existing Lead, Interaction, or Sale scope. Only `page` and `format` query keys are accepted.
- `customer-phones/`: scoped list/create/retrieve/update. List accepts exact positive `customer` ID after role scope, plus standard search, ordering, and pagination. Customer ownership is checked. `normalized_phone` and `is_active` are server-owned and must persist as ASCII `+98[1-9][0-9]{9}`; global active uniqueness and shape are database-backed. No DELETE.
- `POST customer-phones/{id}/deactivate/`: scoped safe transition. It clears active and primary state, preserves the row, audits the action, and returns HTTP 409 `conflict` when already inactive.

## Leads and assignment

- `leads/`: scoped list/create/retrieve/update. Ownership/status fields are read-only. Notes permit at most 4,000 characters. No DELETE.
- `GET leads/assignees/`: Sales Manager, Company IT, or Platform Admin only. Returns paginated minimal identity fields for active clean Sales Agent CRM identities; it does not expose user-administration fields or invent Team boundaries.
- `GET leads/work-queue/`: Sales Agent only. Returns only Leads currently assigned to the authenticated agent; dated follow-ups sort first by nearest `next_follow_up_at`, then assigned records without a date. Managers use the company Lead list, not this personal endpoint.
- `GET leads/{id}/assignment-history/`: paginated append-oriented assignment history after the same role/object scope as Lead retrieve. Out-of-scope direct IDs return 404.
- `POST leads/{id}/reassign/`: Sales Manager, Company IT, or Platform Admin; body has `to_user` and optional `reason`; target must be an active Sales Agent CRM identity, so staff/superuser/group/direct-permission rows cannot be assigned; atomic history and audit.

## Interactions, products, sales

- `interactions/`: scoped list/create/retrieve. Create requires exact `direction` (`inbound` or `outbound`) and a nonblank `outcome` of at most 80 characters. Notes permit at most 4,000 characters. A non-null `next_follow_up_at` updates the locked assigned Lead through the Interaction service in the same transaction. Interaction records are append-only through the API. No update or DELETE.
- `products/`: authenticated read. Sales Manager, Company IT, or Platform Admin create/update. Description permits at most 4,000 characters.
- `POST products/{id}/deactivate/`: Sales Manager, Company IT, or Platform Admin.
- `sales/`: scoped list/create/retrieve. Notes permit at most 4,000 characters. Creation snapshots product price and amount. No generic update/delete.
- `POST sales/{id}/cancel/`: Sales Manager, Company IT, or Platform Admin; optional reason; audited without raw reason text. The central cancel/correct service rejects correction until correction rules are approved.

## Internal sales documents and postal status

- `GET/POST sales-documents/`, `GET sales-documents/{id}/`: internal operational document only; never an accounting Invoice. Sales Manager, Company IT, and Platform Admin register. Sales Agent reads only rows reachable through its scoped Customer or own Sale. No PATCH, PUT, or DELETE.
- Registration requires Customer, unique bounded single-line internal document number, and bounded single-line initial postal status; Sale is optional and must belong to Customer. Province, city, postal code, address, registration actor/time, and active state are server-owned snapshots/state.
- List filters: exact `postal_status`, `province`, `city`, `is_active`; plus search, ordering, and pagination.
- `POST sales-documents/{id}/transition-postal-status/`: elevated roles only. Requires a different nonblank status, appends history, updates current status, and writes safe audit atomically. No unapproved fixed status vocabulary or transition graph is claimed.
- `GET sales-documents/{id}/postal-history/`: paginated append-only history after the same document scope. `POST sales-documents/{id}/deactivate/` is elevated-only and preserves all rows.
- `GET reports/sales-documents/`: required half-open registration period plus optional exact province/city/current-postal-status/active filters. Returns total, counts by snapshotted province/city, and counts by current postal status. Deactivated rows remain included unless `is_active` is supplied. Scope matches document API. No XLSX was approved.

## After-sales requests

- `GET/POST after-sales/`, `GET after-sales/{id}/`: Sales Manager, Company IT, and Platform Admin see/manage all company cases. A Sales Agent in the fixed `after_sales` workstream lists and retrieves assigned cases only. Normal sales-workstream agents get an empty collection and direct IDs return 404. No PATCH, PUT, or DELETE.
- Create requires Customer, subject, description, and bounded single-line initial status. Sale and operational SalesDocument are optional and each must belong to Customer. Creator, close time, timestamps, and history are server-owned. Only an active clean after-sales Sales Agent may be assigned.
- List filters are exact `status`, positive `assigned_to`, and boolean `is_closed`, plus search, ordering, and pagination. Standard unknown/repeated query guards apply.
- `GET after-sales/assignees/` and `POST after-sales/{id}/assign/` are elevated-only. Assignment/reassignment locks the case and eligible operator, rejects closed/same assignment, and atomically appends safe history/audit.
- `POST after-sales/{id}/transition-status/` is allowed to elevated roles and the currently assigned after-sales operator. It rejects closed/same/blank/multiline status and appends history/audit atomically. Exact status vocabulary and graph remain unresolved; no enum is claimed.
- `POST after-sales/{id}/close/` is elevated-only and final because reopen semantics were not supplied. `GET after-sales/{id}/history/` reuses the case selector and is append-only.
- After-sales operators get no Customer, Lead, Interaction, Product, Sale, sales-document, performance, or postal-report API scope. The case response embeds only the bounded relation labels needed by its panel.

## User-performance report and XLSX

- `GET reports/user-performance/`: returns exact per-user `customers_created_count`, `sales_count`, `sales_amount`, and `average_sale_amount` rows.
- `GET exports/user-performance.xlsx`: returns the same scoped rows and filters as an XLSX workbook. Content type is `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`; filename is `kariz-user-performance.xlsx`.
- Required filters are `period_start` inclusive and `period_end` exclusive. Both must be ISO 8601 timestamps with an explicit timezone offset. Values are normalized to UTC and returned as `Z` timestamps.
- Optional `user_id` selects one permitted CRM-compatible account row. A Sales Agent may select only self. Sales Manager, Company IT, and Platform Admin may select fixed-role active or otherwise-clean inactive accounts for history, but staff/superuser/group/direct-permission rows remain excluded. A hidden and a missing user produce the same safe validation response.
- Optional positive `sales_product_id` applies only to confirmed Sale rows already inside the actor's report scope. It does not perform a global Product existence lookup. An unknown ID, or an ID with no permitted matching Sale, returns zero Sale metrics while Customer creation count stays unchanged; this prevents Product-ID probing and preserves inactive historical Sale matches.
- Customer count uses `Customer.created_by` and `created_at` inside the half-open period. Sale metrics use `Sale.sold_by`, `sold_at`, and confirmed rows only; cancelled Sales are excluded.
- Money values have two decimal places. Average Sale amount is `sales_amount / sales_count`, quantized to `0.01` with `ROUND_HALF_UP`; zero Sales returns `0.00`.
- Unknown keys, repeated query keys, naive timestamps, reversed/empty periods, non-positive IDs, and out-of-scope users return the standard safe validation envelope. Positive Product IDs with no scoped match return a normal zero-Sale result. Both successful formats return `Cache-Control: private, no-store`.
- XLSX uses stable machine identifiers for columns, exact two-decimal money text cells, a `filters` sheet with the normalized query, frozen headers, an autofilter, and formula-prefix escaping for user text. Text preserves cents at the maximum supported money range instead of accepting Excel binary-number loss. Final Persian labels, numeric-cell/style choice, and Jalali presentation are not claimed.

## System and schema

- `GET activity-logs/`, `GET activity-logs/{id}/`: read-only. Platform Admin sees all safe rows. Company IT scope uses stored actor/account-object role snapshots from action time, hides Platform Admin actor/target and protected role-change rows, and fails closed on legacy non-system-actor or account-target rows with blank snapshots. Sales Manager limited-audit semantics remain unresolved, so Manager and Sales Agent fail closed. No create/update/delete route.

Browser routes use the same queryset and object guards as the API: `/products/`, `/products/{id}/`, `/sales/`, `/sales/{id}/`, `/sales-documents/`, `/sales-documents/{id}/`, `/reports/user-performance/`, `/reports/sales-documents/`, `/activity-logs/`, and `/activity-logs/{id}/`. Sales Agent Product pages are read-only and hide inactive Products. Sale creation requires an active Product and sends only Lead, Product, quantity, and notes; price snapshot, total, Customer, seller, status, and timestamps remain server-derived. Report pages build requests from their maintained filter forms. ActivityLog pages are read-only and limited to Company IT and Platform Admin with the same direct-ID hiding rules as the API.
- `GET health/live/`: public process liveness.
- `GET health/ready/`: public PostgreSQL readiness; 503 on database failure. `health/` remains a readiness compatibility route.
- `GET schema/`, `GET docs/`: mapped only when `ENABLE_API_DOCS` is true and then limited to active authenticated users. Base settings follow `DEBUG`, test settings enable the flag, and production forces it false. Production therefore removes both URL patterns, so the interactive documentation and its remote browser assets cannot render there. Controlled schema generation remains a build/test command.

Undefined Lead status actions, generic/conversion/call-outcome reports, final human-facing XLSX presentation, and exact after-sales business status transitions remain absent until authoritative rules are complete.

Unknown request keys and server-controlled keys are rejected. Collection/detail update routes use PATCH, not PUT. Validation remains field-shaped under the standard DRF error convention. The bundled Nginx edge discards caller-supplied forwarding chains and sends its direct peer address to the application. Production schema/docs routes stay absent even for Platform Admin.

The application limits login to 10 attempts per minute. User create/update/role change, Customer and CustomerPhone deactivation, Product writes/deactivation, Lead reassignment, Sale create/cancel, after-sales create/assignment/status/close, performance report/XLSX, and ActivityLog reads use one combined 30 requests-per-minute authenticated-user scope. Production keeps this cache in bounded `/tmp` storage shared by all workers in the approved single web container. A multi-container web topology needs an approved shared throttle store and new runtime proof before scale-out.
