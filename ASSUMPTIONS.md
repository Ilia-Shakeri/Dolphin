# Assumptions and unresolved decisions

## Source state

- `BACKEND_SPEC.md` is present and is the current provisional authoritative business source. New explicit user decisions override it.
- The older named backend prompt and frontend context files are absent under canonical or obvious suffixed root names. Their absence does not block work covered by the specification and current approved documents.
- The repository now has Git metadata and an initial commit. New source and durable goal documents still need a reviewed baseline commit.
- The repository contains both the active Django backend and a large static template tree. The active served frontend entry point is not yet proven; language and branding cleanup must first build a reference manifest.

## Confirmed safe implementation choices

- PostgreSQL is the production source of truth. In-memory SQLite is used only for fast host-side logic tests.
- Same-origin session authentication and CSRF are used.
- Fixed CRM roles are `sales_agent`, `sales_manager`, `company_it`, and `platform_admin`.
- The deployment is single-tenant with a separate database per client company.
- Historical business records have no ordinary hard-delete route.
- One Customer may have many Leads. Initial Lead assignment method remains unresolved.
- Active normalized phone identity must be unique across Customers unless a later approved shared-number conflict workflow replaces that rule.
- Reports may implement only the exact unambiguous metrics defined in `BACKEND_SPEC.md`; generic customer and conversion metrics remain blocked.
- The active product interface is Persian-only and uses Kariz branding.
- The bundled production topology has one Nginx proxy hop in front of an unexposed application service.

## Business decisions still needed

- Initial Lead assignment method.
- Final Lead statuses and transitions.
- Final Interaction direction/outcome sets and qualifying call groupings.
- Generic customer KPI, conversion denominator, and reassignment-history semantics.
- Exact XLSX columns, styling, timezone, and Jalali display rules beyond safe machine-readable dates.
- Team model and Sales Manager team-administration boundaries.
- Sale correction semantics beyond confirmed cancellation.
- Optional after-sales scope and statuses.
- Backup destination and retention policy.
- Capacity target, production host, hostname, certificate, and TLS termination path.

These decisions block only their affected behavior. Independent work continues.
