# ForooshBin frontend reference map

## What this document is

The served Persian RTL UI is built **on the purchased Metronic RTL theme**, not
on a lookalike. This map records, for every served route, which theme reference
it came from and how faithful the result is. It does not make any demo page
operational, and it never sources a business rule from one.

`BACKEND_SPEC.md`, the selectors/services/serializers, and explicit product-owner
decisions define data, authorization, statuses and workflow. The theme defines
appearance and component structure — nothing else.

## The one canonical shell

`layouts/dark-sidebar.html` is the single chosen layout variant. No other demo
shell is mixed in. From it the application takes:

* the app root / page / header / wrapper / sidebar / main / footer skeleton and
  its `data-kt-app-*` body attributes;
* `KTMenu` accordion navigation in the sidebar (`menu-item`, `menu-link`,
  `menu-sub-accordion`, `menu-bullet`, keenicons `ki-duotone` icons);
* `KTDrawer` for the mobile sidebar, toggled by the header button;
* the theme's cards, tables, forms, grid, buttons, badges, alerts and spacing.

Loaded assets, and only these, because they are what the served pages request:

| Asset | Why |
|---|---|
| `plugins/global/plugins.bundle.rtl.css` | Bootstrap RTL base + keenicons font-face |
| `css/style.bundle.rtl.css` | the theme itself; also resolves the Persian IRANSans face |
| `js/scripts.bundle.js` | `KTUtil`, `KTMenu`, `KTDrawer`, `KTScroll` |
| `plugins/global/fonts/keenicons/*` | the icon font the sidebar uses |
| `fonts/IRANSansWeb*` | Persian typography |
| `common/kariz.css` | ForooshBin-only: behaviour, brand, print |
| `common/kariz-app.js` | the application; one handler per `data-page` |

**`plugins.bundle.js` (3.5 MB) is deliberately not loaded.** The pages need
`KTMenu` and `KTDrawer`, which live in `scripts.bundle.js`; they do not use
Bootstrap's JavaScript, because the modals are native `<dialog>`. Nothing on a
served page depends on it, and a served page has zero severe console errors
without it.

## Status vocabulary

| Status | Meaning |
|---|---|
| `TEMPLATE_ADAPTED` | markup adapted from a named theme page |
| `COMPOSED_FROM_COMPONENTS` | no equivalent theme page exists, so the page is assembled only from theme components on the canonical shell |

Every route below sits on the canonical shell, so every one is at minimum a
component composition. `TEMPLATE_ADAPTED` is reserved for pages whose layout
follows a specific theme page.

## Route map

| Route | Template | Theme reference | Components reused | Backend | Status |
|---|---|---|---|---|---|
| `/login/` | `login.html` | `authentication/layouts/corporate/sign-in.html` | split auth root, `w-lg-500px` form column, `fv-row`, `form-control`, `btn btn-primary`, dark brand aside | `POST /api/v1/auth/login/` | `TEMPLATE_ADAPTED` |
| `/` | `home.html` + `includes/performance_panel.inc` | `layouts/dark-sidebar.html`, `dashboards/store-analytics.html`, `dashboards/call-center.html` | `card card-flush` stat cards in `row`/`col-sm-6 col-xl-3`, `card-body`, filter grid, `btn`, `table-row-dashed` | me / work-queue / performance APIs, scoped counts | `TEMPLATE_ADAPTED` |
| `/users/` | `users/list.html` | `apps/user-management/users/list.html` | page head, toolbar, `table-responsive`, `badge`, pagination, `dialog` create form | `GET/POST /api/v1/users/` | `TEMPLATE_ADAPTED` |
| `/users/<id>/` | `users/detail.html` | `apps/user-management/users/view.html` | card + `card-body` forms, `form-select`, danger zone card, session table | `GET/PATCH /api/v1/users/<id>/`, `change-role/`, `sessions/`, `revoke-sessions/` | `TEMPLATE_ADAPTED` |
| `/customers/` | `customers/list.html` | `apps/customers/list.html` | toolbar, search, `table align-middle table-row-dashed`, badges, pagination, XLSX action | `GET/POST /api/v1/customers/`, `exports/customers.xlsx` | `TEMPLATE_ADAPTED` |
| `/customers/<id>/` | `customers/detail.html` | `apps/customers/view.html` | card form grid, related paged panels, deactivate card | Customer `GET/PATCH`, `deactivate/`, phones, related leads/interactions/sales | `TEMPLATE_ADAPTED` |
| `/leads/`, `/leads/<id>/` | `leads/*.html` | `apps/contacts/getting-started.html`, `view-contact.html`, `edit-contact.html` | list toolbar/table, detail card grid, reassign card, history table | `GET/POST /api/v1/leads/`, `reassign/`, `assignment-history/` | `COMPOSED_FROM_COMPONENTS` |
| `/interactions/`, `/interactions/<id>/` | `interactions/*.html` | `apps/contacts/add-contact.html`, `view-contact.html` | create `dialog`, table, read-only detail grid | `GET/POST /api/v1/interactions/` | `COMPOSED_FROM_COMPONENTS` |
| `/products/`, `/products/<id>/` | `products/*.html` | `apps/ecommerce/catalog/products.html`, `add-product.html`, `edit-product.html` | catalogue toolbar, category filter, table, edit card | `GET/POST /api/v1/products/` | `TEMPLATE_ADAPTED` |
| `/product-categories/`, `/…/<id>/` | `product_categories/*.html` | `apps/ecommerce/catalog/categories.html`, `add-category.html`, `edit-category.html` | same catalogue pattern, lifecycle buttons | `GET/POST /api/v1/product-categories/` | `TEMPLATE_ADAPTED` |
| `/warehouses/`, `/warehouses/<id>/` | `warehouses/*.html` | no equivalent theme page | list toolbar/table/pagination, edit card, danger zone | `GET/POST /api/v1/warehouses/` | `COMPOSED_FROM_COMPONENTS` |
| `/stock/`, `/stock/movements/` | `inventory/*.html` | no equivalent theme page | toolbar filters, table, movement `dialog`, transfer `dialog` | `GET /api/v1/stock-items/`, `POST /api/v1/stock-movements/` | `COMPOSED_FROM_COMPONENTS` |
| `/sales/`, `/sales/<id>/` | `sales/*.html` | `apps/ecommerce/sales/listing.html`, `details.html` | order-style list, immutable detail card, controlled cancel | `GET/POST /api/v1/sales/`, `cancel/` | `TEMPLATE_ADAPTED` |
| `/quotations/`, `/orders/`, `/invoices/` and details | `quotations/*`, `orders/*`, `invoices/*` + `includes/document_lines.inc` | `apps/ecommerce/sales/listing.html`, `add-order.html`, `details.html`, `apps/invoices/view/invoice-1.html` | document list toolbar with status filter, totals card, line-item table, status transition buttons, allocation panel | quotation/order/invoice APIs incl. `items/`, `issue/`, `cancel/` | `TEMPLATE_ADAPTED` |
| `…/print/` | `quotations/print.html`, `invoices/print.html` | `apps/invoices/view/invoice-1.html` (layout only) | **deliberately not themed** — see intentional differences | server-rendered from the stored snapshot | `COMPOSED_FROM_COMPONENTS` |
| `…/print.pdf` | same templates in `pdf_mode` | as above | as above | `common/pdf.py` | `COMPOSED_FROM_COMPONENTS` |
| `/payments/`, `/payments/<id>/` | `payments/*.html` | no equivalent theme page | list toolbar, method/status filters, allocation panel, cheque card | payment APIs incl. `allocate/`, `release/` | `COMPOSED_FROM_COMPONENTS` |
| `/cheques/`, `/installments/` | `payments/cheques.html`, `installments.html` | no equivalent theme page | filtered table + pagination | `GET /api/v1/cheques/`, `/installments/` | `COMPOSED_FROM_COMPONENTS` |
| `/sales-documents/`, `/…/<id>/` | `sales_documents/*.html` | `apps/ecommerce/sales/listing.html`, `details.html` | list/detail cards, postal transition form, append-only history table | sales-document APIs | `TEMPLATE_ADAPTED` |
| `/after-sales/`, `/…/<id>/` | `after_sales/*.html` | `apps/support-center/tickets/list.html`, `view.html` | case list with status/assignee filters, detail card, history table | after-sales APIs | `COMPOSED_FROM_COMPONENTS` |
| `/reports/user-performance/` | `reports/user_performance.html` + shared panel | `dashboards/finance-performance.html`, `apps/ecommerce/reports/sales.html` | KPI stat cards, filter grid, chart card, drill-down table, XLSX action | performance JSON / details / XLSX | `TEMPLATE_ADAPTED` |
| `/reports/receivables/`, `/profit/`, `/stock-valuation/` | `reports/*.html` | `apps/ecommerce/reports/view.html`, `sales.html` | stat-card row, filter toolbar, report table, XLSX action | financial report APIs | `TEMPLATE_ADAPTED` |
| `/reports/customer-ledger/` | `reports/customer_ledger.html` | `account/statements.html` | statement toolbar, balance card, paged entry table | `GET /api/v1/customer-ledger/`, `balance/` | `TEMPLATE_ADAPTED` |
| `/reports/sales-documents/`, `/reports/inbound-sms/` | `reports/*.html` | `apps/ecommerce/reports/sales.html` | date/geography filters, grouped tables, stat card | report APIs | `COMPOSED_FROM_COMPONENTS` |
| `/activity-logs/`, `/…/<id>/` | `activity_logs/*.html` | no equivalent theme page | search toolbar, table, read-only detail card, bounded JSON block | `GET /api/v1/activity-logs/` | `COMPOSED_FROM_COMPONENTS` |
| header user menu + `#sessions-dialog` | `base.html` | `layouts/dark-sidebar.html` header navbar + `menu-sub-dropdown` panel | symbol/avatar, `menu-content`, `separator`, `menu-link`; sessions in a native dialog | `GET/POST /api/v1/auth/me/sessions/`, `POST /api/v1/auth/logout/` | `TEMPLATE_ADAPTED` |
| Django error pages | `error.html`, and the denial block in `base.html` | theme card + utilities | centred card, `fs-2hx` status, `btn btn-primary` | Django handlers / API error envelope | `COMPOSED_FROM_COMPONENTS` |

## Intentional differences from the theme

Each of these is a deliberate choice, not an omission.

1. **The header user menu is the theme's panel, opened by the application.**
   The markup, classes and `.show` rule are the theme's own, so it looks and
   behaves like every other Metronic menu. `KTMenu` is not used to open it:
   it positions a dropdown with Popper, which ships only in the plugins bundle
   above. Toggling the class is eight lines in `kariz-app.js` and the anchoring
   is three in `kariz.css` — the same trade as the native dialogs, for the same
   reason. The sidebar accordion still uses `KTMenu`, which needs no Popper.

2. **Modals are native `<dialog>`, not `.modal`.** The theme's modal needs
   Bootstrap's JavaScript, which would mean shipping the 3.5 MB plugins bundle
   for one component. `<dialog>` is real, focusable, closes on Escape, and needs
   no library. `kariz.css` gives it the theme's card surface — about ten lines,
   the only place a theme component is re-created.
3. **The print and PDF pages load no theme bundle at all.** Paper has no dark
   sidebar, no cards and no hover states, and a printed invoice must look the
   same whatever the theme is doing on screen. Their stylesheet is
   self-contained in `kariz.css`.
4. **No theme-mode switcher, no language selector, no social sign-in, no
   sign-up, no password-reset link, no notification or avatar drawer.** All
   exist in the theme; all are absent by Client-1 policy, and a control may
   appear only when its action is real.
5. **The performance chart is a plain bar list, not the theme's chart widget.**
   The theme charts through amCharts loaded from a CDN, which is forbidden — no
   served page may reach a third-party host. The bars are drawn from real report
   values.
6. **`data-module` attributes are kept on navigation links.** They are not a
   theme convention; they are how the deployment-profile and capability tests
   assert which entries a role may see.
7. **Stable application ids** (`app-sidebar`, `nav-toggle`, `main-content`,
   `app-error`, `global-message`) live alongside the theme's own ids, so tests
   pin behaviour rather than the theme's layout naming.
8. **The whole theme tree is the static root.** Its CSS resolves fonts
   relatively, so the directory shape must survive; a prefixed `STATICFILES_DIRS`
   entry also fails to resolve forward-slash URLs on Windows, where this is
   developed. `collectstatic` still excludes the demo media that no page
   requests.

---

## Appendix — pre-theme screen notes (history)

Kept because it records each screen's backend endpoints, role scope and known
UX gaps in more detail than the route table above. Its "visual reference" column
described pages that were *consulted*; the table above records what is now
actually adapted. Where the two disagree, the table above is current.

## Active page map

| Business screen | Active route and Django template | Active JS handler | Real backend/API endpoint(s) | Allowed role/scope | Exact inspected visual reference | Major current UX/layout gap |
|---|---|---|---|---|---|---|
| Login | `/login/` — `common/templates/common/login.html` | `setupLogin` | `POST /api/v1/auth/login/` | Signed-out users; active clean CRM identities redirect home after login | `authentication/layouts/corporate/sign-in.html` | Maintained page is a compact single card. Reference has richer spacing/indicator layout, but its social login, reset, and signup actions are not approved and must not be copied. |
| Role-aware home/profile | `/` — shared `common/templates/common/home.html` plus `common/templates/common/includes/performance_panel.inc` | `setupDashboard`, `setupProfile`, `setupWorkQueue`, `setupPerformancePanel`; capability cards are server-rendered | Me/work-queue APIs; performance JSON/detail/XLSX APIs; scoped selectors supply card counts | All four active CRM roles; widgets/navigation come from capabilities; Sales workstream gets own/company performance; work queue is Sales Agent only | `index.html` for shell rhythm; role references below | One shared application renders role modes. All shown KPI/chart/table/detail values use real scoped records; after-sales workstream remains isolated from sales reports. |
| Platform Admin home | `/` — shared `home.html` with `dashboard.platform` | `setupProfile` | Me API plus scoped Customer/Lead/Interaction/Sale/User/Audit counts | Full clean CRM identity custody, audit, and all existing business modules | `index.html`, `apps/user-management/users/list.html`, `apps/user-management/users/view.html` | Platform-oriented cards and navigation exist. Infrastructure/runtime telemetry is not implemented. |
| Store manager home | `/` — shared `home.html` with `dashboard.store` and shared performance include | `setupDashboard`, `setupPerformancePanel`, `renderPerformanceChart`, `loadPerformanceDetails` | Me API; company-scoped card counts; performance JSON/details/XLSX; Product choices | Company-wide business/report scope; authorized user/date/Product filters; Sales Agent user management only | `dashboards/store-analytics.html` | Four approved KPI cards, real confirmed-Sale amount chart, same-scope table/details, and states are connected. Comparisons/targets remain unapproved. |
| Agent/call-center home | `/` — shared `home.html` with `dashboard.agent` and shared performance include | `setupDashboard`, `setupWorkQueue`, `setupPerformancePanel`, `loadPerformanceDetails` | Me; work queue; own performance JSON/details/XLSX; active Product choices | Own report rows/details only; no user filter; queue contains currently assigned Leads; products read-only | `dashboards/call-center.html` | Real queue plus own KPI/chart/table/details exist. No other username/count/ID is returned; telephony, automation, and Lead status formulas remain absent. |
| After-sales operator home | `/` — shared `home.html` with `dashboard.after_sales` | `setupDashboard`, `setupProfile` | Me API; server-scoped assigned AfterSalesRequest count | Active clean `sales_agent` with `after_sales` workstream only; no sales-domain navigation/report data | `index.html` shell rhythm and `apps/user-management/users/view.html` summary-card analogue only | Assigned-case count and direct panel link are real. No exact curated after-sales dashboard reference exists. |
| User list / administration | `/users/` — `common/templates/common/users/list.html` | `setupUsers` | `GET/POST /api/v1/users/` | Manager: Sales Agent only; Company IT: non-platform; Platform Admin: all clean CRM identities; Sales Agent denied | `apps/user-management/users/list.html` | Real search/create/pagination and role-aware title exist. Bulk actions remain unapproved. |
| User detail / role control | `/users/<id>/` — `common/templates/common/users/detail.html` | `setupUserDetail` | `GET/PATCH /api/v1/users/<id>/`; `POST .../change-role/` | Manager may edit/deactivate/reactivate agents only and has no role form; Company IT cannot target Platform Admin; Platform Admin controls all fixed roles | `apps/user-management/users/view.html` | Real edit, status toggle, and allowed role control exist. Avatar/session panels are not implemented. |
| Customer list/create | `/customers/` — `common/templates/common/customers/list.html` | `setupCustomers`, `customerRow` | `GET/POST /api/v1/customers/` | All roles through `customers_for`; agent sees created or Lead-assigned Customers | `apps/customers/list.html` | Real search/order/page/create exists. Reference filter menu/table density is richer; bulk/export/governed-category controls remain unapproved. |
| Customer detail/profile | `/customers/<id>/` — `common/templates/common/customers/detail.html` | `setupCustomerDetail`, `phoneRow` | Customer `GET/PATCH`; `POST .../deactivate/`; CustomerPhone CRUD/deactivate; related `leads/`, `interactions/`, `sales/` | Same scoped Customer visibility; deactivate is manager/technical/platform only | `apps/customers/view.html` | Maintained page has real fields, phones, and related paged records. Reference summary/sidebar/tab hierarchy is absent; billing/tax/account links from reference are out of scope. |
| Lead list/create | `/leads/` — `common/templates/common/leads/list.html` | `setupLeads`, `leadRow` | `GET/POST /api/v1/leads/`; Customer/Product lookup | All roles through `leads_for`; agent sees assigned or own unassigned Leads | `apps/contacts/getting-started.html` as a visual list/card analogue only | Follow-up is visible in the real table. No exact curated Lead reference exists; pipeline, priority, archive, conversion, and stage UI remain blocked. |
| Lead detail/reassignment | `/leads/<id>/` — `common/templates/common/leads/detail.html` | `setupLeadDetail` | `GET/PATCH /api/v1/leads/<id>/`; `GET assignees/`; `GET assignment-history/`; `POST reassign/` | Agent edits assigned Lead fields only; elevated roles may reassign | `apps/contacts/view-contact.html`, `apps/contacts/edit-contact.html` as visual analogues only | Real Customer-profile link, edit/history/reassign exist. No exact Lead detail reference, timeline, stage strip, or opportunity panel exists. |
| Interaction list/create | `/interactions/` — `common/templates/common/interactions/list.html` | `setupInteractions`, `interactionRow` | `GET/POST /api/v1/interactions/`; scoped Lead and current-user lookup | Agent only for assigned Leads; elevated roles company-wide | `apps/contacts/getting-started.html`, `apps/contacts/add-contact.html` as visual analogues only | Manual inbound/outbound form, visible follow-up, and authorized Lead quick-open exist. No timeline/calendar/telephony UI is implied. |
| Interaction detail | `/interactions/<id>/` — `common/templates/common/interactions/detail.html` | `setupInteractionDetail` | `GET /api/v1/interactions/<id>/` | Same `interactions_for` backend scope | `apps/contacts/view-contact.html` as a visual detail analogue only | Read-only detail is flat. Timeline, meeting, task, responsible person, and calendar contracts remain unapproved. |
| Product Category list/create | `/product-categories/` — `common/templates/common/product_categories/list.html` | `setupProductCategories`, `productCategoryRow` | `GET/POST /api/v1/product-categories/` | Agent reads active Categories only; manager/technical/platform manage | `apps/ecommerce/catalog/categories.html`, `apps/ecommerce/catalog/add-category.html` | Real search/status/order/page/table/create states exist. Flat Category only; reference hierarchy, media, and Product-count semantics are not copied. |
| Product Category detail | `/product-categories/<id>/` — `common/templates/common/product_categories/detail.html` | `setupProductCategoryDetail`, `fillProductCategory` | Category `GET/PATCH`; `POST deactivate/`; `POST reactivate/` | Agent read-only active direct-ID scope; elevated roles edit/lifecycle | `apps/ecommerce/catalog/edit-category.html` | Real immutable code, edit, lifecycle, conflict, loading/error states exist. No tree or media panel is approved. |
| Product list/create | `/products/` — `common/templates/common/products/list.html` | `setupProducts`, `productRow` | `GET/POST /api/v1/products/`; active Category lookup | Agent reads active Products/Categories only; manager/technical/platform manage | `apps/ecommerce/catalog/products.html`, `apps/ecommerce/catalog/add-product.html` | Real Category filter/selection, brand, barcode, search/status/order/page and table states exist. Media, stock, pricing history, discount, and variants remain absent by contract. |
| Product detail | `/products/<id>/` — `common/templates/common/products/detail.html` | `setupProductDetail`, `fillProduct` | `GET/PATCH /api/v1/products/<id>/`; `POST .../deactivate/`; active Category lookup | Agent read-only active scope; elevated roles edit/deactivate | `apps/ecommerce/catalog/edit-product.html` | Maintained form exposes real Category/brand/barcode fields. Reference media/stock/sidebar sections remain excluded until their own contracts exist. |
| Sale list/create | `/sales/` — `common/templates/common/sales/list.html` | `setupSales`, `saleRow` | `GET/POST /api/v1/sales/`; scoped Lead/Product lookup | Agent sees own Sales and creates from assigned Lead; elevated roles company-wide | `apps/ecommerce/sales/listing.html`, `apps/ecommerce/sales/add-order.html` as layout analogues only | Authorized Lead quick-open and preselection exist. Current Sale is not an Order/Invoice; richer order states/history remain out of scope. |
| Sale detail/cancel | `/sales/<id>/` — `common/templates/common/sales/detail.html` | `setupSaleDetail`, `fillSale` | `GET /api/v1/sales/<id>/`; `POST .../cancel/` | Agent own read; manager/technical/platform may cancel with audit | `apps/ecommerce/sales/details.html` as a layout analogue only | Maintained page is an immutable flat record plus controlled cancel. Reference order tabs, shipment, invoice, and payment panels are out of scope. |
| Internal sales-document list/create | `/sales-documents/` — `common/templates/common/sales_documents/list.html` | `setupSalesDocuments`, `salesDocumentRow` | `GET/POST /api/v1/sales-documents/`; scoped Customer/Sale lookups | Agent scoped read-only; manager/technical/platform register and see company rows | `apps/ecommerce/sales/listing.html`, `apps/ecommerce/sales/add-order.html` as layout analogues only | Real search/exact filters/table/create exist. This is not an Order or accounting Invoice. Exact postal vocabulary, tracking, PDF, tax, and payments remain absent. |
| Internal sales-document detail/postal history | `/sales-documents/<id>/` — `common/templates/common/sales_documents/detail.html` | `setupSalesDocumentDetail`, `fillSalesDocument`, `loadPostalHistory` | Document `GET`; `POST .../transition-postal-status/`; `GET .../postal-history/`; `POST .../deactivate/` | Agent scoped read-only; manager/technical/platform transition/deactivate | `apps/ecommerce/sales/details.html` as a detail-layout analogue only | Immutable geography/address snapshot and append-only history are real. No carrier panel or inferred status graph exists. |
| After-sales case list/create | `/after-sales/` — `common/templates/common/after_sales/list.html` | `setupAfterSales`, `afterSalesRow` | `GET/POST /api/v1/after-sales/`; elevated Customer/Sale/SalesDocument lookup; `GET /after-sales/assignees/` | Manager/technical/platform all company cases and create; after-sales operator assigned-only read; sales operator denied | `apps/user-management/users/list.html`, `apps/contacts/getting-started.html`, `apps/ecommerce/sales/listing.html` as bounded layout analogues only | Real search/status/assignee/open filters and create dialog exist. No exact curated after-sales page exists; status vocabulary/SLA/refund/return/attachments are absent by contract. |
| After-sales case detail/history | `/after-sales/<id>/` — `common/templates/common/after_sales/detail.html` | `setupAfterSalesDetail`, `fillAfterSales`, `loadAfterSalesHistory` | Case `GET`; `POST assign/`, `transition-status/`, `close/`; `GET history/` | Elevated all company controls; assigned after-sales operator status only; direct IDs masked | `apps/user-management/users/view.html`, `apps/contacts/view-contact.html`, `apps/ecommerce/sales/details.html` as detail/history analogues only | Real immutable relations, status control, assignment, final close, and append-only history exist. No exact curated after-sales detail reference or approved reopen graph exists. |
| User performance report | `/reports/user-performance/` — `common/templates/common/reports/user_performance.html` plus shared performance include | `setupUserPerformance`, `setupPerformancePanel`, `renderPerformanceChart`, `loadPerformanceDetails`, `reportQuery` | performance JSON; paged same-scope details; XLSX | Agent self only; manager/technical/platform approved company/user rows; same filter/scope drives aggregate and details | `dashboards/finance-performance.html`, `apps/ecommerce/reports/sales.html`, `apps/ecommerce/reports/view.html` | Four approved KPI cards, real confirmed-Sale amount chart, filters, table, drill-down, loading/empty/error and JSON/UI/XLSX parity exist. No P&L, receivable, target, or unapproved formula exists. |
| Sales-document/postal report | `/reports/sales-documents/` — `common/templates/common/reports/sales_documents.html` | `setupSalesDocumentReport`, `salesDocumentReportQuery` | `GET /api/v1/reports/sales-documents/` | Agent scoped document counts; manager/technical/platform company counts | `apps/ecommerce/reports/sales.html`, `apps/ecommerce/reports/view.html` as report-layout analogues only | Real half-open date and exact geography/status/active filters plus two grouped tables exist. XLSX and charts were not approved. |
| Inbound SMS report | `/reports/inbound-sms/` — `common/templates/common/reports/inbound_sms.html` | `setupInboundSMSReport`, `inboundSMSReportQuery`, `renderInboundSMSChart`, `loadInboundSMSDrilldown`, `showInboundSMSMessage` | `GET /api/v1/reports/inbound-sms/`; `GET .../drilldown/`; `GET .../messages/<id>/` | Manager/technical/platform company scope only; Sales Agent has no menu, aggregate, filter, or direct-row access | No exact curated SMS reference exists. `apps/ecommerce/reports/sales.html` is the approved report-toolbar/table layout analogue only. | Real date/provider/recipient/state filters, Tehran date/hour count/chart, same-scope drill-down, message detail, and loading/empty/error states exist. No body, webhook, live adapter, outbound SMS, or provider branding is present. |
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
- `apps/ecommerce/catalog/categories.html`
- `apps/ecommerce/catalog/add-category.html`
- `apps/ecommerce/catalog/edit-category.html`
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
- No exact curated after-sales list, case detail, or operator dashboard page was identified. The bounded user/contact/sale pages above were inspected for layout rhythm only; no support-center page was opened or silently substituted.
- No separate exact Platform Admin dashboard reference exists. The maintained route intentionally remains one shared role-aware dashboard/profile page rather than duplicated frontends.
- Vendor stylesheet/plugin implementation remains intentionally excluded. The maintained `common/static/common/kariz.css` is the only active stylesheet inspected in this phase.
