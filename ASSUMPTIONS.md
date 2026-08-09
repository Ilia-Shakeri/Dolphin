# Assumptions and blockers

## Blocking authority gaps

- `BACKEND_SPEC.md` and the two named backend context files are absent from the active repository on 2026-08-09.
- No existing Django project, migration history, Git metadata, or production-data evidence is present.
- Lead status values and transitions are undefined. The schema stores a blank status and exposes no status-transition action until the authoritative specification exists.
- Interaction outcome and direction enums are undefined. Both remain optional text values with no inferred choices.
- Team/company boundaries and the Company IT user-administration scope are undefined. No Team model is created.
- Shared-household phone policy is undefined. Active normalized phones are unique per customer, but not globally unique.
- Rules after Customer deactivation are undefined. Existing visibility stays intact, and no new-child prohibition is invented yet.
- KPI formulas, reassignment attribution, date boundaries, and zero-denominator behavior are undefined. Performance reports and XLSX export are deferred.
- After-sales, Invoice, postal, SMS, ecommerce, payment, inventory, tax, return, refund, shipping, and external sync work is deferred.

## Safe implementation choices

- PostgreSQL is the production source of truth. SQLite is not configured.
- Same-origin session authentication and CSRF are used.
- Timestamps use Django timezone-aware fields.
- Historical business objects have no ordinary destroy endpoint.
- Sales Agents see a customer when they created it or currently own one of its leads. They see only currently assigned leads, interactions for those leads, their own sales, and active products.
- Sales Managers, Company IT, and Platform Admin can see operational records. Company IT operational writes stay blocked while its company scope remains unresolved. Only Sales Manager and Platform Admin may reassign leads, manage products, or cancel sales.
- Lead creation leaves assignment empty unless an elevated actor explicitly assigns it through the service.
