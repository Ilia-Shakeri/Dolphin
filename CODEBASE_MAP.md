# Codebase map

## Repository and boundaries

- Root: `Kariz-CRM`.
- Active backend: first-party Django apps plus `config`, deployment files, and backend docs.
- Static template archive: root HTML and large `account/`, `apps/`, `authentication/`, `assets/`, `src/`, layout/demo trees. It is not copied into the backend image because `.dockerignore` excludes it. Served status is unproven.
- Never review dependency/vendor/minified/media/font/binary/cache trees as application logic.

## Django apps

| App | Responsibility | Main entry points | Main data |
|---|---|---|---|
| `accounts` | Custom user, session auth/profile, user and role administration | auth URLs, user router/viewset | User |
| `sales` | Operational CRM records and transitions | sales router/viewsets, services/selectors | Customer, CustomerPhone, Lead, history, Interaction, Product, Sale |
| `auditlog` | Sensitive activity persistence and safe payload filtering | service calls from account/sales transitions | ActivityLog |
| `common` | Base model, permissions, request context, strict input, phone normalization, health | middleware and health routes | shared behavior |
| `reports` | Exact predefined metrics and XLSX | not yet implemented | read-only aggregates |
| `config` | Settings, URL root, WSGI/ASGI, PostgreSQL test guard | application process | runtime configuration |

## Request, auth, and audit flow

```text
Browser -> Nginx request ID / rate / proxy headers
        -> RequestContextMiddleware
        -> Security / session / CSRF / authentication
        -> active-user permission
        -> role-scoped viewset/queryset
        -> strict serializer
        -> locked service transition
        -> model/database constraint
        -> safe ActivityLog with same request ID
        -> response with one request ID
```

## URL map

- `/api/v1/auth/login/`, `/logout/`, `/me/`.
- `/api/v1/users/` and role-change action.
- `/api/v1/customers/` and deactivate action.
- `/api/v1/customer-phones/`.
- `/api/v1/leads/` and reassign action.
- `/api/v1/interactions/` read/create only.
- `/api/v1/products/` and deactivate action.
- `/api/v1/sales/` and cancel action.
- `/api/v1/health/live/`, `/health/ready/`, compatibility `/health/`.
- Authenticated `/api/v1/schema/` and `/api/v1/docs/`.
- Report and XLSX routes: pending Phase 5.

## Core data flow

```text
User creates Customer
  -> CustomerPhone normalized and duplicate checked
  -> Customer gets one or many Leads
  -> elevated role assigns/reassigns Lead
  -> assignment history and audit append atomically
  -> assigned user records Interaction
  -> assigned/elevated user marks confirmed Sale
  -> Sale snapshots product price and computed amount
  -> exact role-scoped report aggregates Customer/Sale rows
  -> same query result renders JSON and XLSX
```

## Deployment topology

```text
Host :80 -> Nginx
              -> /static/ from named static volume
              -> Gunicorn web:8000
                       -> PostgreSQL db:5432 on internal Compose network

One-shot migrate service:
  wait for DB -> migrate -> collectstatic -> exit -> web starts
```

- Docker image uses Python slim, pinned compatible dependency ranges, non-root user, and Gunicorn.
- PostgreSQL data uses a named persistent volume.
- Application service is exposed only inside Compose.
- Real TLS edge, backup destination, and log aggregation remain unresolved.

## External dependencies and integrations

- Runtime Python: Django, REST framework, schema generator, PostgreSQL driver, Gunicorn.
- No approved external SMS, telephony, ecommerce, payment, shipping, tax, inventory, or website sync integration.
- No Redis, task queue, microservice, or dynamic permission builder.

## Active UI and language/brand state

- The large template tree is present but not shipped by the backend container.
- `TEMPLATES.DIRS` is empty and no Kariz runtime template route is yet mapped.
- Phase 1 must prove whether any external static deployment uses root `index.html` or another path.
- Phase 6/7 may create a small active Kariz-specific Persian shell if no active first-party UI exists; no archive deletion occurs until a Git-backed reference manifest proves safety.
