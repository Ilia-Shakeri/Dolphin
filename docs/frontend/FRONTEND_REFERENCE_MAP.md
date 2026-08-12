# Kariz CRM frontend reference map

## Authority and use

- This map covers the maintained Persian RTL Django UI. It does not make demo/theme pages operational.
- `BACKEND_SPEC.md`, backend selectors/services/serializers, and explicit user decisions define data, authorization, statuses, and workflows.
- The exact theme HTML files below were inspected only in bounded ranges for layout and UX patterns. No rule, permission, metric, entity, status, route, or action was inferred from them.
- Active architecture: `common/ui_urls.py` routes to `common/ui_views.py`; templates extend `common/templates/common/base.html`; `body[data-page]` selects one handler in `common/static/common/kariz-app.js`; same-origin session/CSRF calls reach `/api/v1/`; `common/static/common/kariz.css` supplies the maintained lightweight RTL shell.
- Stable backend names remain unchanged. Customer is displayed as `مشتری` / `مشتریان`. Role labels are `بازاریاب (کال سنتر)`, `مدیر فروشگاه`, `مدیر فنی مشتری`, and `مدیر پلتفرم`.

## Active page map

| Business screen | Active route and Django template | Active JS handler | Real backend/API endpoint(s) | Allowed role/scope | Exact inspected visual reference | Major current UX/layout gap |
|---|---|---|---|---|---|---|
| Login | `/login/` — `common/templates/common/login.html` | `setupLogin` | `POST /api/v1/auth/login/` | Signed-out users; active clean CRM identities redirect home after login | `authentication/layouts/corporate/sign-in.html` | Maintained page is a compact single card. Reference has richer spacing/indicator layout, but its social login, reset, and signup actions are not approved and must not be copied. |
| Own profile/home | `/` — `common/templates/common/home.html` | `setupProfile` | `GET/PATCH /api/v1/auth/me/`; logout in shell uses `POST /api/v1/auth/logout/` | All four active CRM roles; own profile only | `index.html` for shell rhythm | Current route is a profile page, not an operational dashboard. No fake KPI or role dashboard is present. |
| Store manager home | `/` — `common/templates/common/home.html` for `sales_manager` | `setupProfile` | `GET/PATCH /api/v1/auth/me/` | `sales_manager`; current backend operational scopes remain company-wide | `dashboards/store-analytics.html` | No dedicated store-manager KPI cards, charts, filters, or drill-down. Metrics remain blocked by report decisions. |
| Agent/call-center home | `/` — `common/templates/common/home.html` for `sales_agent` | `setupProfile` | `GET/PATCH /api/v1/auth/me/` | `sales_agent`; own/assigned operational scope | `dashboards/call-center.html` | No dedicated queue, call KPI, lead workload, or follow-up dashboard. Telephony metrics and dashboard formulas are not approved. |
| User list / platform administration | `/users/` — `common/templates/common/users/list.html` | `setupUsers` | `GET/POST /api/v1/users/` | `company_it` sees/manages non-platform CRM users; `platform_admin` sees/manages all clean CRM users | `apps/user-management/users/list.html` | Maintained list has real search/create/pagination but not the reference filter menu, bulk toolbar, or dense table treatment. Bulk role/user work is not approved. |
| User detail / role control | `/users/<id>/` — `common/templates/common/users/detail.html` | `setupUserDetail` | `GET/PATCH /api/v1/users/<id>/`; `POST /api/v1/users/<id>/change-role/` | `company_it` cannot see, target, grant, or manage `platform_admin`; `platform_admin` has full CRM custody; last active Platform Admin guard applies | `apps/user-management/users/view.html` | Maintained page has real edit/role/deactivate controls but no reference summary sidebar/tabs. Avatar/session panels are not implemented. |
| Customer list/create | `/customers/` — `common/templates/common/customers/list.html` | `setupCustomers`, `customerRow` | `GET/POST /api/v1/customers/` | All roles through `customers_for`; agent sees created or Lead-assigned Customers | `apps/customers/list.html` | Real search/order/page/create exists. Reference filter menu/table density is richer; bulk/export/governed-category controls remain unapproved. |
| Customer detail/profile | `/customers/<id>/` — `common/templates/common/customers/detail.html` | `setupCustomerDetail`, `phoneRow` | Customer `GET/PATCH`; `POST .../deactivate/`; CustomerPhone CRUD/deactivate; related `leads/`, `interactions/`, `sales/` | Same scoped Customer visibility; deactivate is manager/technical/platform only | `apps/customers/view.html` | Maintained page has real fields, phones, and related paged records. Reference summary/sidebar/tab hierarchy is absent; billing/tax/account links from reference are out of scope. |
| Lead list/create | `/leads/` — `common/templates/common/leads/list.html` | `setupLeads`, `leadRow` | `GET/POST /api/v1/leads/`; Customer/Product lookup | All roles through `leads_for`; agent sees assigned or own unassigned Leads | `apps/contacts/getting-started.html` as a visual list/card analogue only | No exact curated Lead reference exists. Maintained page is table/dialog based; pipeline, priority, archive, conversion, and stage UI remain blocked. |
| Lead detail/reassignment | `/leads/<id>/` — `common/templates/common/leads/detail.html` | `setupLeadDetail` | `GET/PATCH /api/v1/leads/<id>/`; `GET assignees/`; `GET assignment-history/`; `POST reassign/` | Agent edits assigned Lead fields only; elevated roles may reassign | `apps/contacts/view-contact.html`, `apps/contacts/edit-contact.html` as visual analogues only | No exact Lead detail reference. Current page has real edit/history/reassign but no timeline, stage strip, or opportunity panel. |
| Interaction list/create | `/interactions/` — `common/templates/common/interactions/list.html` | `setupInteractions`, `interactionRow` | `GET/POST /api/v1/interactions/`; scoped Lead and current-user lookup | Agent only for assigned Leads; elevated roles company-wide | `apps/contacts/getting-started.html`, `apps/contacts/add-contact.html` as visual analogues only | No exact Interaction reference. Current page has a real append-only manual call form, not timeline/calendar/telephony UI. |
| Interaction detail | `/interactions/<id>/` — `common/templates/common/interactions/detail.html` | `setupInteractionDetail` | `GET /api/v1/interactions/<id>/` | Same `interactions_for` backend scope | `apps/contacts/view-contact.html` as a visual detail analogue only | Read-only detail is flat. Timeline, meeting, task, responsible person, and calendar contracts remain unapproved. |
| Product list/create | `/products/` — `common/templates/common/products/list.html` | `setupProducts`, `productRow` | `GET/POST /api/v1/products/` | Agent reads active Products only; manager/technical/platform manage | `apps/ecommerce/catalog/products.html`, `apps/ecommerce/catalog/add-product.html` | Maintained search/status/order/table aligns with the reference pattern at smaller scale. Category, media, stock, pricing history, and expanded form groups are absent by contract. |
| Product detail | `/products/<id>/` — `common/templates/common/products/detail.html` | `setupProductDetail`, `fillProduct` | `GET/PATCH /api/v1/products/<id>/`; `POST .../deactivate/` | Agent read-only active scope; elevated roles edit/deactivate | `apps/ecommerce/catalog/edit-product.html` | Maintained form is one card. Reference split sidebar/media/category layout cannot be used until those fields and file policy exist. |
| Sale list/create | `/sales/` — `common/templates/common/sales/list.html` | `setupSales`, `saleRow` | `GET/POST /api/v1/sales/`; scoped Lead/Product lookup | Agent sees own Sales and creates from assigned Lead; elevated roles company-wide | `apps/ecommerce/sales/listing.html`, `apps/ecommerce/sales/add-order.html` as layout analogues only | Current Sale is not an Order/Invoice. Date toolbar and richer reference order states/history must not be copied as business behavior. |
| Sale detail/cancel | `/sales/<id>/` — `common/templates/common/sales/detail.html` | `setupSaleDetail`, `fillSale` | `GET /api/v1/sales/<id>/`; `POST .../cancel/` | Agent own read; manager/technical/platform may cancel with audit | `apps/ecommerce/sales/details.html` as a layout analogue only | Maintained page is an immutable flat record plus controlled cancel. Reference order tabs, shipment, invoice, and payment panels are out of scope. |
| User performance report | `/reports/user-performance/` — `common/templates/common/reports/user_performance.html` | `setupUserPerformance`, `reportQuery` | `GET /api/v1/reports/user-performance/`; `GET /api/v1/exports/user-performance.xlsx` | Agent self only; manager/technical/platform approved company/user rows | `dashboards/finance-performance.html`, `apps/ecommerce/reports/sales.html`, `apps/ecommerce/reports/view.html` | Real filters/table/XLSX exist. KPI cards, charts, comparison, drill-down, and domain reports lack approved formulas. |
| Audit list | `/activity-logs/` — `common/templates/common/activity_logs/list.html` | `setupActivityLogs`, `activityLogRow` | `GET /api/v1/activity-logs/` | `company_it` gets non-platform-safe audit; `platform_admin` gets full CRM audit | No exact curated audit-list reference found; `apps/user-management/users/view.html` supplies only a partial summary-card pattern | Current real table/search/page is intentionally plain. No exact audit reference, advanced event facets, or saved filters are available. |
| Audit detail | `/activity-logs/<id>/` — `common/templates/common/activity_logs/detail.html` | `setupActivityLogDetail` | `GET /api/v1/activity-logs/<id>/` | Same backend audit selector and direct-ID scope | No exact curated audit-detail reference found | Current safe read-only fields and bounded JSON are functional; richer diff/timeline presentation has no exact approved reference. |
| Error shell | Django 400/403/404/500 through `common/templates/common/error.html` and guarded `base.html` states | Generic `showError` handles API errors on active pages | Django error handlers plus stable API error envelope | Scope follows the requested page/API; no data is rendered after denial | No exact curated error reference found | Maintained error card is functional and branded; no richer exact reference is available. |

## Exact reference files inspected

- `authentication/layouts/corporate/sign-in.html`
- `index.html`
- `dashboards/store-analytics.html`
- `dashboards/call-center.html`
- `dashboards/finance-performance.html`
- `apps/user-management/users/list.html`
- `apps/user-management/users/view.html`
- `apps/customers/list.html`
- `apps/customers/view.html`
- `apps/contacts/getting-started.html`
- `apps/contacts/add-contact.html`
- `apps/contacts/edit-contact.html`
- `apps/contacts/view-contact.html`
- `apps/ecommerce/catalog/products.html`
- `apps/ecommerce/catalog/add-product.html`
- `apps/ecommerce/catalog/edit-product.html`
- `apps/ecommerce/sales/listing.html`
- `apps/ecommerce/sales/details.html`
- `apps/ecommerce/sales/add-order.html`
- `apps/ecommerce/reports/sales.html`
- `apps/ecommerce/reports/view.html`

Inspection was limited to titles, forms, content containers, cards, toolbars, tables, filters, detail layout, and chart placeholders. Referenced plugin, media, font, minified/bundled, generated/build, vendor-internal, and secret files were not opened.

## Missing exact references

- No exact curated Lead page was identified; Contacts pages are only visual analogues.
- No exact curated Interaction/timeline page was identified; Contacts pages are only visual analogues.
- No exact curated ActivityLog list/detail page was identified.
- No separate maintained or exact reference page exists for store-manager and agent homes beyond the inspected dashboard references; the live route remains the shared profile page.
- Vendor stylesheet/plugin implementation remains intentionally excluded. The maintained `common/static/common/kariz.css` is the only active stylesheet inspected in this phase.
