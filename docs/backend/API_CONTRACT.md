# API contract

Base path: `/api/v1/`. Authentication: Django session cookie plus CSRF. Unsafe requests require CSRF outside test clients. Normal API request and response bodies use JSON only; form, multipart, and HTML negotiation are rejected. The XLSX export is the sole approved binary response and still returns the shared JSON error envelope on failure. Unauthenticated requests return 403 under DRF session authentication. A valid CRM identity must be active, use one fixed CRM role, have no staff/superuser flag, and have no Django group or direct permission; server identities that fail this rule are rejected at login and every CRM permission gate. Validation errors keep field-shaped details and add `error.code` plus `error.request_id`. Stable codes include `validation_error`, `conflict`, `authentication_failed`, `permission_denied`, `not_found`, `not_acceptable`, `method_not_allowed`, `unsupported_media_type`, `parse_error`, `payload_too_large`, `throttled`, and `server_error`. True uniqueness or current-state clashes use HTTP 409 and `conflict`. Malformed JSON or JSON deeper than 32 container levels returns HTTP 400 `parse_error`. Request bodies are limited to 64 KiB at both the application and bundled edge; larger requests return HTTP 413 `payload_too_large`. An unhandled `/api/` fault returns safe JSON with HTTP 500, `server_error`, and the same request ID; exception text, stack, internal path, SQL, and payload are not returned. Every application response has `X-Request-ID`, including HTTPS redirects. The bundled Nginx edge redirects HTTP application traffic to its exact configured public HTTPS host, terminates only TLS 1.2/1.3 with externally mounted certificate files, sends fixed `X-Forwarded-Proto: https`, owns the edge request ID, and overwrites forwarding headers. Direct application requests keep a caller request ID only when it uses 1-64 letters, digits, dots, underscores, or hyphens; otherwise Django makes a new value. The ID is for tracing, not authority. Audited request work stores the same ID.

## Authentication

- `POST auth/login/`: username and password; creates session. Inactive/invalid credentials and any server identity with staff/superuser/group/direct-permission state are rejected without exposing which identity rule failed. Application and Nginx rate limits protect repeated attempts.
- `POST auth/logout/`: authenticated; clears session.
- `GET/PATCH auth/me/`: current safe profile. Patch permits first name, last name, phone, and email only; it locks and safely audits changed field names.

## Users

- `GET/POST users/`, `GET/PATCH users/{id}/`: Company IT or Platform Admin. Lists and direct IDs contain clean CRM account rows, including inactive rows so approved administrators can reactivate them; staff/superuser/group/direct-permission identities remain hidden. Inactive actors still fail every API gate. Sales Manager user-directory access fails closed until a Team model and exact team scope are approved. New and reset passwords pass Django password validators.
- `POST users/{id}/change-role/`: Company IT can grant through `company_it`; Platform Admin can grant any fixed CRM role. Staff/superuser/groups/permissions are never writable. Demoting the last active Platform Admin CRM identity returns HTTP 409 `conflict`.
- `PATCH users/{id}/` with `is_active=false`: deactivating the last active Platform Admin CRM identity returns HTTP 409 `conflict`. A second active Platform Admin counts only when it also passes the CRM-identity guard.

## Customers and phones

- `customers/`: scoped list/create/retrieve/update. Create accepts optional nested `phone`. Address permits at most 2,000 characters; notes permit at most 4,000. No DELETE.
- `POST customers/{id}/deactivate/`: Sales Manager, Company IT, or Platform Admin. Sales Agents cannot deactivate Customers.
- `customer-phones/`: scoped list/create/retrieve/update. Customer ownership is checked. `normalized_phone` is server-owned and must persist as ASCII `+98[1-9][0-9]{9}`; global active uniqueness and shape are database-backed. No DELETE.

## Leads and assignment

- `leads/`: scoped list/create/retrieve/update. Ownership/status fields are read-only. Notes permit at most 4,000 characters. No DELETE.
- `POST leads/{id}/reassign/`: Sales Manager, Company IT, or Platform Admin; body has `to_user` and optional `reason`; target must be an active Sales Agent CRM identity, so staff/superuser/group/direct-permission rows cannot be assigned; atomic history and audit.

## Interactions, products, sales

- `interactions/`: scoped list/create/retrieve. Create requires exact `direction` (`inbound` or `outbound`) and a nonblank `outcome` of at most 80 characters. Notes permit at most 4,000 characters. Interaction records are append-only through the API. No update or DELETE.
- `products/`: authenticated read. Sales Manager, Company IT, or Platform Admin create/update. Description permits at most 4,000 characters.
- `POST products/{id}/deactivate/`: Sales Manager, Company IT, or Platform Admin.
- `sales/`: scoped list/create/retrieve. Notes permit at most 4,000 characters. Creation snapshots product price and amount. No generic update/delete.
- `POST sales/{id}/cancel/`: Sales Manager, Company IT, or Platform Admin; optional reason; audited without raw reason text. The central cancel/correct service rejects correction until correction rules are approved.

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
- `GET health/live/`: public process liveness.
- `GET health/ready/`: public PostgreSQL readiness; 503 on database failure. `health/` remains a readiness compatibility route.
- `GET schema/`, `GET docs/`: mapped only when `ENABLE_API_DOCS` is true and then limited to active authenticated users. Base settings follow `DEBUG`, test settings enable the flag, and production forces it false. Production therefore removes both URL patterns, so the interactive documentation and its remote browser assets cannot render there. Controlled schema generation remains a build/test command.

Undefined Lead status actions, generic/conversion/call-outcome reports, final human-facing XLSX presentation, and after-sales routes remain absent until authoritative rules are complete.

Unknown request keys and server-controlled keys are rejected. Collection/detail update routes use PATCH, not PUT. Validation remains field-shaped under the standard DRF error convention. The bundled Nginx edge discards caller-supplied forwarding chains and sends its direct peer address to the application. Production schema/docs routes stay absent even for Platform Admin.

The application limits login to 10 attempts per minute. User create/update/role change, Customer deactivation, Product writes/deactivation, Lead reassignment, Sale create/cancel, performance report/XLSX, and ActivityLog reads use one combined 30 requests-per-minute authenticated-user scope. Production keeps this cache in bounded `/tmp` storage shared by all workers in the approved single web container. A multi-container web topology needs an approved shared throttle store and new runtime proof before scale-out.
