# Assumptions and unresolved decisions

## Source state

- `BACKEND_SPEC.md` is present and is the current provisional authoritative business source. New explicit user decisions override it.
- The older named backend prompt and frontend context files are absent under canonical or obvious suffixed root names. Their absence does not block work covered by the specification and current approved documents.
- The repository has Git metadata, initial commit `ef1c7f4`, and reviewed durable baseline commit `50a978a`.
- The active first-party UI is the Django-served `/` shell under `common`, plus the Django admin surface. The separate large static template archive is not in `TEMPLATES.DIRS`, is excluded from the backend image, and was not edited or deleted. That proves it is unserved by the current repository-controlled stack, not unused by every possible external deployment.

## Confirmed safe implementation choices

- PostgreSQL is the production source of truth. In-memory SQLite is used only for fast host-side logic tests.
- Same-origin session authentication and CSRF are used.
- Fixed CRM roles are `sales_agent`, `sales_manager`, `company_it`, and `platform_admin`.
- CRM identity excludes any Django staff, superuser, group-linked, or direct-permission account. Server administration and CRM administration are separate trust planes.
- API object IDs are server-created. Write payloads reject client-supplied `id` values.
- The deployment is single-tenant with a separate database per client company.
- Historical business records have no ordinary hard-delete route.
- Normal API request bodies are capped at 64 KiB and JSON nesting at 32 container levels. Customer address is capped at 2,000 characters; Customer, Lead, Interaction, Product, and Sale free-text notes/description fields are capped at 4,000. These are defensive technical bounds, not new workflow meaning.
- Login is limited to 10 attempts per minute. User administration, Customer deactivation, Product writes, Lead reassignment, Sale create/cancel, report/export reads, and audit reads share a defensive 30 requests-per-minute user limit. Production uses one bounded file cache shared by the three Gunicorn workers in the single approved web container; horizontal web scaling needs an approved shared throttle store first.
- One Customer may have many Leads. Initial Lead assignment method remains unresolved.
- Active normalized phone identity must be unique across Customers unless a later approved shared-number conflict workflow replaces that rule.
- Canonical normalized phones use ASCII `+98` followed by ten ASCII digits. Persian and Arabic input digits may be folded before validation; other Unicode digit forms are rejected.
- Reports may implement only the exact unambiguous metrics defined in `BACKEND_SPEC.md`; generic customer and conversion metrics remain blocked.
- Report money outputs use two decimal places. Computed averages quantize to `0.01` with `ROUND_HALF_UP`; a zero denominator returns `0.00`.
- The current XLSX is a machine-readable foundation: stable identifier headers, exact two-decimal money text, UTC ISO filter values, exact JSON/filter parity, and spreadsheet-formula prefix defense. Text avoids Excel binary-number precision loss at the maximum supported money range. Final Persian labels, numeric-cell/style choices, Jalali presentation, and extra columns remain separate approval work.
- The active product interface is Persian-only and uses Kariz branding.
- Bundled Nginx terminates TLS on 443, redirects HTTP to one fixed public host, owns checked HSTS, and proxies one hop to the unexposed application service.
- Compose splits database init superuser, one-shot migration owner, runtime application, and read-only backup logins. The same guarded bootstrap prepares roles/passwords, then runs one locked owner/ACL unit before migration and again as an exact post-migration finalizer. Future tables, sequences, and routines get no application grant by default. Web receives only the application credential and no schema-owner rights; the profile-only backup job receives only the backup credential.
- PostgreSQL data and backup storage use two required external volume names. The approved live names, mounts, access, and reuse still need host evidence.
- Existing-data deploys make and restore-check a current-compatible recovery point before candidate environment/image/database/role/schema changes. The default restore drill has no network or database secret, mounts backup data read-only, and uses a bounded tmpfs cluster. A proven empty new install is the only no-backup branch.
- Production Compose has no local build path and accepts only digest-qualified application, PostgreSQL, and Nginx image references. The Dockerfile also requires a digest-qualified Python base. Real reviewed digest values and built-artifact identity remain external proof; no value is guessed in source.
- The edge write-stop is a reversible operator gate that blocks POST/PUT/PATCH/DELETE while reads and health remain available. It is not a database recovery, data-integrity, or authorization substitute.
- Audit rows created before role snapshots stay blank. Company IT cannot see those unknown rows; Platform Admin can. No current-role guess or unsafe backfill is used.
- Exact Python versions constrain package choice. Package hashes, real reviewed image digests, a clean Linux build, SBOM, and current dependency/container scans remain unproved.

## Business decisions still needed

- Initial Lead assignment method.
- Final Lead statuses and transitions.
- Final Interaction outcome codes and qualifying call groupings. Direction is fixed to inbound/outbound, while the required outcome remains bounded free text until codes are approved.
- Generic customer KPI, conversion denominator, and reassignment-history semantics.
- Final human-facing XLSX columns/labels, styling, and Jalali display rules beyond the current machine-readable UTC foundation.
- Team model and Sales Manager team-administration boundaries.
- Sale correction semantics beyond confirmed cancellation.
- Optional after-sales scope and statuses.
- Backup destination and retention policy.
- Legacy audit-row visibility or an authoritative role-at-action backfill source.
- Capacity target, production host, hostname, certificate files, and certificate renewal owner/path.

These decisions block only their affected behavior. Independent work continues.
