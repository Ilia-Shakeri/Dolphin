# Kariz CRM project handoff

این فایل تنها منبع زنده وضعیت، پیشرفت، blocker، شاهد، تصمیم باز و اقدام دقیق بعدی پروژه است. `BACKEND_SPEC.md` قرارداد پیاده‌سازی است؛ اسناد `docs/backend/` قراردادهای فنی و اسناد `docs/ops/` runbookهای عملیاتی هستند و هیچ‌کدام جایگزین وضعیت زنده این فایل نیستند.

## CURRENT SNAPSHOT — 2026-08-12

- Active phase: Client-1 foundation correction — terminology, frontend reference, and current truth; `DONE` locally. External release/runtime proof remains separate.
- Git HEAD: `fa32e5287e8caa10eba688f2d84efe23a6cc9947`.
- Git status: dirty working tree; no commit created. This slice changes `AGENTS.md`, `BACKEND_SPEC.md`, this handoff, the root roadmap, synthetic-UAT command/test, maintained UI views/templates/script/tests, branding guard, and adds `docs/frontend/FRONTEND_REFERENCE_MAP.md`. Exact final status is recorded in the foundation checkpoint below.
- Implemented core: session login/logout/current profile; fixed-role user management/deactivation/role-change; Customer/CustomerPhone create/read/edit/deactivate and scoped related records; Lead CRUD/manual assignment/history; append-only manual Interaction; Product CRUD/deactivate/filter; operational Sale create/cancel; four-metric user-performance JSON/XLSX; scoped read-only ActivityLog; Persian RTL maintained UI connected to real APIs.
- Current role map: `sales_agent` = `بازاریاب (کال سنتر)`; `sales_manager` = `مدیر فروشگاه`; `company_it` = `مدیر فنی مشتری`; `platform_admin` = `مدیر پلتفرم`. `platform_admin` keeps highest CRM custody. `company_it` cannot grant, target, see, or manage Platform Admin through user administration.
- Current Customer meaning: actual store/customer/client contact; visible label `مشتری` / `مشتریان`. `Customer` model/API/table/field/stable identifiers stay unchanged. A Sales Agent is a User, never a Customer.
- Active frontend architecture: 19 maintained templates under `common/templates/common/`; one inherited Persian RTL shell; `common/ui_urls.py` and `common/ui_views.py`; one `body[data-page]` handler map in `common/static/common/kariz-app.js`; one maintained stylesheet `common/static/common/kariz.css`; same-origin Session/CSRF calls to real `/api/v1/` endpoints; relevant API/UI/browser tests under active first-party apps.
- Frontend reference policy: exact curated theme HTML files are read-only visual/layout/UX references only. The allowlist and page-to-reference/API/role/gap map are in `AGENTS.md` and `docs/frontend/FRONTEND_REFERENCE_MAP.md`. Plugin/media/font/minified/generated/vendor-internal trees remain excluded.
- Resolved decisions: Customer-versus-marketer terminology; all four Persian role labels; fixed role-code retention; Platform Admin custody; Company IT privilege ceiling; C1-DEC-ROLE-001. The old section 26 reverse mapping and old C1-1 role-ambiguity/24-open-decision counts are historical and superseded.
- Still open: `23` consolidated decision IDs remain wholly open. Highest gate: C1-DEC-GOV-001, C1-DEC-SEAT-001, C1-DEC-TEAM-001, and C1-DEC-AFTER-001. Lead workflow, calendar/task, document/postal, detailed reports, SMS/provider, inventory/finance/files/search/integrations/late platform work, runtime proof, and delivery staging remain blocked by their recorded contracts.
- Verification truth: Django check, migration drift, 284-test full suite, OpenAPI validation, JavaScript syntax, 4 browser tests, branding guard, collectstatic dry-run, active terminology guards, and diff checks pass. Exact evidence and Git status are in section 33.
- Exact next phase: close GOV/SEAT/TEAM/AFTER decisions and run C1-2. Do not add a new business model before its remaining semantic gate is approved.

## 1. مرز وضعیت و تحویل

| جریان | وضعیت زنده | معنی |
|---|---|---|
| **CURRENT CORE RELEASE** | `production candidate; external verification pending` | هسته repository تست شده است؛ PostgreSQL زنده، Docker، Nginx، TLS، مرورگر، backup/restore، load و زیرساخت مقصد هنوز proof بیرونی می‌خواهند. |
| **FULL 74-CAPABILITY PRODUCT** | `work in progress` | 74 ردیف ممیزی دارد: 46 ردیف دارای پوشش backend و 28 ردیف دارای HTML shell؛ هیچ‌کدام بدون `VERIFIED_END_TO_END` به معنی تحویل کاربر نهایی نیست. |
| **DELIVERY TARGET** | `Client-1 expanded target; contracts partial` | همه خانواده‌های نام‌برده در منبع نهایی Client-1 داخل هدف نهایی هستند؛ هسته موجود carry-forward است، موارد علامت‌خورده در `FINAL_WAVE_LOW` می‌مانند و هیچ رفتار تازه بدون قرارداد و acceptance مصوب ساخته یا تحویل‌شده اعلام نمی‌شود. |

تنها وضعیت `VERIFIED_END_TO_END` در همین فایل، قابلیت قابل تحویل به کاربر نهایی را ثابت می‌کند. `IMPLEMENTED_BACKEND`، `HTML_SHELL` یا حضور route/page به‌تنهایی تحویل نیست.

## 2. مرجع‌ها و قانون نگهداری

- `AGENTS.md`: قواعد کار، امنیت، scope و verification.
- `BACKEND_SPEC.md`: قرارداد authoritative فعلی محصول و backend.
- `KARIZ_PROJECT_HANDOFF.md`: تنها وضعیت زنده، checkboxها، blockerها، evidence و resume point.
- `docs/backend/ENTITY_CATALOG.md`: تعریف entityها.
- `docs/backend/RELATIONSHIPS.md`: تعریف رابطه‌ها.
- `docs/backend/ERD.mmd`: ERD.
- `docs/backend/API_CONTRACT.md`: قرارداد HTTP/API.
- `docs/backend/DISCOVERY.md`: مرز source/runtime.
- `docs/ops/`: runbookهای deploy، TLS، backup/restore، rollback، incident، UAT، load و scan؛ این اسناد status tracker نیستند.
- `docs/KARIZ_CAPABILITIES_FOR_INVOICE_FA.txt`: فهرست ممیزی/فاکتور؛ proof تحویل نیست.

محتوای unique و actionable دو سند موقت `KARIZ_PRODUCT_COMPLETION_ROADMAP.md` و `docs/KARIZ_FUTURE_BACKEND_WORK_FA.md` در این فایل ادغام و آن دو حذف شدند. سند root دیگری برای status، roadmap، worklog، blocker یا readiness باقی نمانده است. تاریخ اسناد قدیمی حذف‌شده در Git قابل بازیابی است.

## 3. قابلیت‌های هسته عملیاتی فعلی

- ورود، خروج، پروفایل جاری و قطع فوری دسترسی کاربر غیرفعال.
- چهار نقش ثابت `sales_agent`، `sales_manager`، `company_it` و `platform_admin` با queryset/object authorization در backend.
- User و مدیریت کنترل‌شده کاربر/نقش، جدا از `is_staff`، `is_superuser`، Django groups و server access.
- Customer و CustomerPhone با چند شماره ایرانی نرمال‌شده، شماره اصلی، active state و جلوگیری از duplicate فعال.
- Lead با source، campaign/batch، محصول مورد علاقه، تخصیص/انتقال دستی، تاریخچه و audit.
- Interaction دستی ورودی/خروجی و اطلاعات پیگیری برای Lead مجاز.
- Product با قیمت جاری؛ read-only برای Sales Agent و deactivate برای نقش مجاز.
- Sale تاییدشده با quantity، snapshot قیمت/محصول، total، cancel کنترل‌شده و audit؛ Sale فاکتور حسابداری نیست.
- ActivityLog امن و فقط‌خواندنی در scope مجاز، همراه request ID.
- گزارش predefined عملکرد کاربر: `customers_created_count`، `sales_count`، `sales_amount` و `average_sale_amount`.
- فیلترهای تاییدشده بازه زمانی، کاربر مجاز و محصول، با parity بین JSON و XLSX.
- API نسخه‌دار زیر `/api/v1/`، Session Authentication، CSRF، OpenAPI، health live/ready و error envelope پایدار.
- رابط فعال فارسی، RTL و با برند `Kariz CRM` / `کاریز`.
- استقرار single-tenant با PostgreSQL، Docker Compose و Nginx، به شرط عبور proofهای بیرونی.

`AfterSalesRequest` فقط optional و فقط پس از انتخاب صریح scope و تایید قرارداد `BACKEND_SPEC.md` است.

هدف توسعه‌یافته Client-1، blockerها، اولویت‌ها و dependency order در بخش 20 ثبت شده‌اند. فهرست هسته فعلی به معنی حذف قابلیت‌های تازه از هدف نهایی نیست.

## 4. قابلیت‌های خارج از ادعای عملیاتی فعلی

خانواده‌های نام‌برده در منبع نهایی Client-1 از این فهرست حذف نمی‌شوند؛ آن‌ها داخل هدف نهایی ولی تا تصمیم و acceptance دقیق `BLOCKED_DECISION` یا `BLOCKED_EXTERNAL` هستند. موارد عمومی مثل public multi-tenant SaaS یا زیرساخت تاییدنشده فقط با requirement صریح جدا مجاز می‌شوند.

- Invoice، InvoiceItem، پیش‌فاکتور، سند حقوقی، مالیات، تخفیف و PDF عملیاتی.
- Order/OrderItem، ecommerce و اتصال وب‌سایت/فروشگاه.
- Payment، ledger، بدهی/طلب، چک، قسط، درگاه، settlement، refund و reconciliation.
- Warehouse، inventory، stock movement، purchase cost، چندقیمتی و profit.
- Shipping/postal status/history، delivery proof، return و refund workflow.
- SMS، email، WhatsApp، telephony/call-center، recording و provider integration.
- فایل/پوشه عملیاتی، attachment storage، malware scan و signed download.
- Inbox، chat، ticket/support، FAQ و AfterSales بدون تصویب صریح.
- Activity/Task/Project/Meeting/Calendar/recurrence/reminder خودکار تا تایید قرارداد دامنه.
- Opportunity/Pipeline، Lead conversion، forecast و saved/global search تا تایید قرارداد.
- dynamic report builder، automation engine، import گروهی XLSX و PWA.
- public sign-up، dynamic role/permission builder، multi-tenant SaaS، client source fork، microservice، Kubernetes، Redis یا Celery بدون requirement صریح.
- هر صفحه vendor/demo که workflow تاییدشده Kariz ندارد.

وجود HTML نمایشی برای موارد بالا مجوز توسعه یا ادعای تحویل نیست.

## 5. وضعیت قابلیت و acceptance مشترک

هر capability فقط یکی از stateهای زیر را در این فایل می‌گیرد:

- `IMPLEMENTED_BACKEND`: backend وجود دارد؛ UI متصل claim نمی‌شود.
- `HTML_SHELL`: فقط مرجع رابط وجود دارد؛ قابل استفاده نیست.
- `IN_PROGRESS`: slice تاییدشده باز است.
- `BLOCKED_DECISION`: قرارداد کسب‌وکار تصویب نشده است.
- `BLOCKED_EXTERNAL`: source آماده و proof محیط واقعی لازم است.
- `VERIFIED_END_TO_END`: backend، UI واقعی، امنیت، تست و proof runtime لازم پاس شده است.
- `DISABLED_BY_PROFILE`: capability قبلا end-to-end تایید شده ولی در deployment مشخص عمدا غیرفعال است.

گیت `VERIFIED_END_TO_END` برای هر قابلیت:

- [ ] قرارداد و مثال پذیرش تاییدشده؛ هیچ قانون از demo page استنباط نشده است.
- [ ] entity/relationship/ERD/API/discovery مرتبط به‌روز است.
- [ ] migration additive، preflight، compatibility، recovery و data impact روشن است.
- [ ] transition و multi-row write در service تراکنشی است.
- [ ] API، validation، error، pagination/filter و OpenAPI کامل است.
- [ ] هر چهار role، direct-ID، queryset/object scope و server-owned fields تست شده‌اند.
- [ ] audit امن است و secret، token، cookie، password یا raw private payload ندارد.
- [ ] رابط واقعی فارسی/RTL با empty/loading/error/conflict/throttle/permission و desktop/mobile کار می‌کند.
- [ ] unit/service/API/CSRF/PostgreSQL/browser و query/bounds tests مرتبط پاس است.
- [ ] backup/restore/upgrade/rollback/monitoring اثر قابلیت را پوشش می‌دهد.
- [ ] UAT با داده synthetic پاس و evidence دقیق در همین فایل ثبت شده است.
- [ ] demo data، dead control، fake success، broken link و browser console/network error باقی نمانده است.

## 6. سابقه فازهای CURRENT CORE V1

این فازها سابقه ساخت هسته فعلی هستند، نه برنامه کامل Client-1. ترتیب زنده Client-1 در بخش 20 جایگزین next action این سابقه شده است.

- [x] **V0 — Backend core:** schema، service، API، authorization، audit، report/XLSX و repository tests ساخته شد.
- [x] **V1 — Truth consolidation:** status/spec/roadmap/blocker truth در همین handoff ادغام شد؛ دو سند موقت حذف و disclaimer قابلیت اصلاح شد.
- [x] **V2 — Connected application shell:** shell نگهداری‌شده فقط routeهای واقعی auth/profile/user را نشان می‌دهد؛ API client same-origin/CSRF، navigation فارسی/RTL، brand guard و stateهای خطا/خالی repository-complete است.
  - [x] **V2-A — HTML branding guard:** همه 207 فایل HTML/template first-party فعلی، شامل archive و templateهای shell، با scan خودکار guard شدند؛ batch اولیه archive برابر 202 فایل بود.
  - [x] **V2-B — Connected auth/user shell:** login/logout/me، user list/detail/create/edit/deactivate و change-role چهار نقش ثابت به API واقعی وصل شد؛ public signup، role builder، dead control و fake success ندارد.
- [x] **V3 — Core browser flows:** auth/user/customer/phone/Lead/Interaction/Product/Sale/report/audit به backend واقعی وصل و role/browser tests پاس شود.
  - [x] auth و user در repository با unit/API و headless Chrome desktop/mobile پاس است؛ release-target browser proof هنوز `EXT-006` است.
  - [x] Customer و CustomerPhone در repository به list/detail/create/edit/search/order/pagination/deactivate و چند تلفن واقعی وصل است؛ normalization، duplicate/primary conflict، چهار role، direct ID و headless Chrome پاس است.
  - [x] Lead و Interaction در repository به list/detail/create/edit مجاز/filter/search/order/pagination، تخصیص/انتقال دستی، history و ثبت تماس دستی ورودی/خروجی وصل است؛ rule تازه برای status/outcome/team/auto-assignment ساخته نشد.
  - [x] Product، Sale، report و audit رابط واقعی و browser flow دارند.
- [ ] **V4 — Safe low-ambiguity completion:** filterهای دقیق، customer overview، assignment history read API، audit summary و bounded bulk deactivate فقط در صورت انطباق با spec اجرا شود.
- [ ] **V5 — External core proof:** PostgreSQL، Compose، Nginx، TLS، static، health، write-stop، browser، backup/restore، load و scan روی release دقیق پاس شود.
- [ ] **V6 — Scoped V1 UAT/cutover:** profile تحویل، migration/reconciliation در صورت نیاز، UAT، training، rollback و owner sign-off پاس شود.

## 7. رجیستر FULL 74-CAPABILITY PRODUCT — dependency target، نه proof تحویل

این رجیستر فقط هدف و dependency order محصول کامل را حفظ می‌کند. منبع نهایی Client-1 خانواده‌های نام‌برده را داخل هدف آورده است؛ هیچ phase آینده بدون قرارداد، scope جزئی و تصمیم مکتوب شروع نمی‌شود.

- [ ] **R0 — Trace:** به هر 74 ردیف capability ID، state، owner، dependency، decision و proof وصل شود.
- [ ] **R1 — Repeatable runtime:** release reproducible، PostgreSQL/Compose/Nginx proof، artifact digest، scan، staging و monitor بیرونی.
- [ ] **R2 — Profile/job foundation:** registry/profile امضاشده و fail-closed، capability manifest، job/outbox durable و application shell واقعی.
- [ ] **R3 — Current core end-to-end:** همان V2 تا V4؛ ابتدا backend موجود به browser واقعی وصل شود.
- [ ] **R4 — Customer 360/activity/security:** فقط پس از قرارداد Customer merge، activity، reminder، reset، 2FA و session/device.
- [ ] **R5 — Lead/pipeline/insight:** فقط پس از state machine، Team، conversion، Opportunity و KPI approval.
- [ ] **R6 — Catalog/inventory:** فقط پس از قواعد category/variant/price/warehouse/stock و concurrency.
- [ ] **R7 — Order/invoice/documents:** فقط پس از قرارداد حقوقی، numbering، tax، discount، Decimal، correction و PDF.
- [ ] **R8 — Finance:** فقط پس از قرارداد payment/ledger/cheque/installment/reconciliation/idempotency.
- [ ] **R9 — Shipping/returns/support/files:** فقط پس از ownership، retention، storage، malware، SLA و recovery policy.
- [ ] **R10 — Communication/providers:** فقط پس از consent، opt-out، template، delivery، retry، idempotency، cost و credential ownership.
- [ ] **R11 — Import/export/report/automation/integration/PWA:** فقط پس از bounds، provider، replay، reconciliation و offline policy.
- [ ] **R12 — Full product verification:** full-profile repository/PostgreSQL/browser/security/load/recovery/UAT؛ بدون P0/P1.
- [ ] **R13 — Portable appliance:** یک Linux/amd64 Compose contract برای Linux و Windows Server Hyper-V appliance؛ support matrix، signed/offline bundle، common operator verbs و cross-host restore.
- [ ] **R14 — Client site:** server/router/ISP/VPN/MFA/VLAN/TLS/UPS/monitoring/off-host backup survey و proof.
- [ ] **R15 — Client delivery:** signed feature profile، migration، UAT، training، pilot و cutover.
- [ ] **R16 — Lifecycle:** hypercare، patch، monitoring، recovery drill، deprecation و profile change control.

قواعد unique این رجیستر:

- feature availability از role permission و object scope جدا است؛ دسترسی موثر = feature enabled + role allowed + object in scope.
- profile غیرفعال نباید data/history را حذف یا external side effect ایجاد کند؛ unknown profile/dependency readiness را fail می‌کند.
- full profile باید پیش از profile کوچک‌تر همان release پاس شود؛ غیرفعال‌کردن feature ناتمام، full product را کامل نمی‌کند.
- full product فقط با همان release bundle، image digest، schema، backup format و operator contract روی hostهای پشتیبانی‌شده claim می‌شود.
- Linux مستقیم و Windows Server با Hyper-V appliance proof جدا می‌خواهند؛ pass یک مسیر، مسیر دیگر را ثابت نمی‌کند.
- remote seller access ترجیحا VPN فردی + MFA -> HTTPS 443 است؛ PostgreSQL، Gunicorn، SSH، RDP و Hyper-V public نمی‌شوند.
- backup فقط پس از checksum، off-host copy و restore در database تازه pass است؛ volume، RAID، VM checkpoint یا VHDX copy به‌تنهایی backup نیست.

## 8. گیت‌های انتشار

### CURRENT CORE RELEASE

- [x] repository-controlled schema/service/API/auth/audit/report work بدون P0/P1 شناخته‌شده.
- [x] full local suite: 263 pass؛ 6 PostgreSQL-only روی SQLite عمدا skip؛ 3 flow در headless Chrome پاس.
- [x] Django check، migration drift، OpenAPI، collectstatic dry run، dependency check، image-ref validator و script parsers طبق proof ثبت‌شده پاس.
- [ ] native PostgreSQL migration/constraint/concurrency.
- [ ] Compose boot/migrate/static/health/API/write-stop/restart/log proof.
- [ ] Nginx/TLS/secure-cookie/CSRF/renewal/external scan.
- [ ] browser desktop/mobile Persian/RTL/brand/role/console proof.
- [ ] real backup + no-network isolated restore.
- [ ] approved load target، monitoring و incident/rollback exercise.

تا تکمیل موارد باز، claim فقط `production candidate; external verification pending` است.

### FULL 74-CAPABILITY PRODUCT

- [ ] هر capability در full profile برابر `VERIFIED_END_TO_END` است.
- [ ] full-profile functional/auth/profile/accessibility/responsive/load/upgrade/rollback/incident/UAT pass است.
- [ ] portable matrix روی Linux و Windows Server release دقیق، همراه cross-host و clean-host restore pass است.
- [ ] target-site network، VPN/TLS، backup، monitoring، owner، training و sign-off pass است.

فقط بعد از تمام گیت‌های full product و سایت دقیق، عبارت `production ready and ready to use` مجاز است.

## 9. معماری، migration و endpointهای موجود

- Django + Django REST Framework + PostgreSQL؛ modular monolith؛ single-tenant و database جدا برای هر شرکت.
- Same-origin Session Authentication + CSRF؛ API base برابر `/api/v1/`.
- UI فعال فعلی: `/login/`، `/`، `/users/`، `/users/<id>/`، `/customers/`، `/customers/<id>/`، `/leads/`، `/leads/<id>/`، `/interactions/`، `/interactions/<id>/` و Django admin؛ navigation فقط routeهای واقعی داخل scope را نشان می‌دهد.
- health: `/api/v1/health/live/` و `/api/v1/health/ready/`.
- migration heads: `accounts.0002_user_role_constraint`، `auditlog.0002_activitylog_role_snapshots` و `sales.0010_interaction_contract`.
- routeهای اصلی: auth login/logout/me، users/change-role، customers/deactivate، customer-phones/deactivate، leads/assignees/reassign/assignment-history، interactions، products، sales/cancel، activity-logs، user-performance JSON و XLSX.
- business history به شکل عادی hard-delete نمی‌شود؛ reassignment، role change و Sale create/cancel در service و audit انجام می‌شود.

## 10. تصمیم‌های کسب‌وکار باز

| ID | تصمیم لازم | رفتار امن فعلی |
|---|---|---|
| BIZ-001 | روش initial Lead assignment | auto assignment ساخته نشده |
| BIZ-002 | status و transition نهایی Lead | transition حدسی وجود ندارد |
| BIZ-003 | outcome و qualifying-call group | direction ثابت؛ outcome متن bounded |
| BIZ-004 | customer/conversion/reassignment KPI | metric مبهم منتشر نمی‌شود |
| BIZ-005 | Team model و Manager boundary | Manager user admin بسته است |
| BIZ-006 | Sale correction semantics | correction رد؛ cancel موجود |
| BIZ-007 | XLSX labels/style/Jalali | export دقیق machine-readable موجود |
| BIZ-008 | After-sales scope | entity/API ساخته نشده |
| BIZ-009 | backup schedule/retention/owner/RTO/RPO | ابزار guard شده؛ policy زنده ندارد |
| BIZ-010 | capacity/load target و abort rule | harness آماده؛ target ندارد |
| BIZ-011 | Manager audit boundary | Manager audit بسته است |
| BIZ-012 | legacy audit backfill یا denial دائمی | Company IT legacy unknown را نمی‌بیند |
| BIZ-013 | deactivate user با Lead فعال | assignee/history خودکار جابه‌جا نمی‌شود |

تصمیم‌های آینده Customer/Activity/Pipeline/Catalog/Inventory/Order/Invoice/Payment/Shipping/Communication/File/Support/Security/Reporting/Automation/Integration/Import/Profile فقط هنگام تصویب expansion scope به blocker فعال تبدیل می‌شوند؛ برای V1 فعلی requirement نیستند.

## 11. blockerهای بیرونی و عملیاتی

| ID | ورودی لازم | proof بسته‌شدن |
|---|---|---|
| EXT-001 | PostgreSQL bin سازگار + Bash | اجرای `scripts/test-postgres.ps1` روی cluster disposable |
| EXT-002 | Docker + image digests + volume names | pull/boot/health/static/API/write-stop proof |
| EXT-003 | Nginx runtime | config و HTTP edge proof |
| EXT-004 | hostname + cert/key path + renewal owner | TLS/redirect/HSTS/scanner proof |
| EXT-005 | runtime و backup واقعی | dump + no-network disposable restore |
| EXT-006 | browser و edge UI | desktop/mobile Persian/RTL/brand/console proof |
| EXT-007 | runtime/scanner digests + isolated scan host | SBOM، vulnerability، dependency، source و TLS evidence |

- OPS-001: current/prior runtime artifacts، محل امن و compatibility owner.
- OPS-002: release/database/security/business/rollback owner و window/abort rule.
- OPS-003: backup scheduler، overlap/timeout، alert، off-host copy، RTO/RPO.
- OPS-004: log retention/access/deletion/alert policy.
- OPS-005: active Platform Admin confirmation یا first-install bootstrap approval.
- OPS-006: write-stop/rollback/incident/cutover/reopen owner و tabletop.

ابزارهای Docker، Nginx و PostgreSQL server/client هنگام آخرین proof روی host موجود نبودند؛ proof زنده claim نشده است.

## 12. branding و license policy

- همه متن و brand فعال project-owned برابر `Kariz CRM` و نام تاییدشده `کاریز` است.
- رابط فعال فارسی-only، RTL و responsive است مگر `BACKEND_SPEC.md` صریحا تغییر کند.
- vendor purchase/preview/demo link، fake data/action و vendor-visible branding در رابط فعال حذف می‌شود.
- شناسه‌های runtime پایدار theme مانند `KTMenu`، `KTDrawer`، `KTUtil` و `data-kt-*` کورکورانه rename نمی‌شوند.
- `LICENSE*`، `NOTICE*`، READMEها و همه notice/licenseهای third-party حفظ می‌شوند؛ brand cleanup مجوز حذف attribution قانونی نیست.
- حذف locale/demo/duplicate فقط پس از manifest دقیق، reference proof، batch کوچک و smoke test انجام می‌شود.
- `scripts/check_html_branding.py` guard اجباری HTML first-party است؛ HTMLهای third-party زیر `src/plugins/keenicons/` فقط attribution/tool demo هستند و تغییر نکردند.

## 13. evidence این مرحله

### فایل‌های بررسی‌شده

- `AGENTS.md`
- `BACKEND_SPEC.md`
- `KARIZ_PROJECT_HANDOFF.md`
- `KARIZ_PRODUCT_COMPLETION_ROADMAP.md`
- `docs/KARIZ_FUTURE_BACKEND_WORK_FA.md`
- `docs/KARIZ_CAPABILITIES_FOR_INVOICE_FA.txt`
- `docs/backend/DISCOVERY.md`
- `docs/ops/DEPLOYMENT.md`
- `docs/ops/DEPENDENCIES.md`
- `docs/ops/RELEASE_CHECKLIST.md`
- `docs/ops/RELEASE_NOTES.md`
- `docs/ops/SOURCE_MANIFEST.md`
- root Markdown manifest و referenceهای status/roadmap در `docs/backend/` و `docs/ops/`

### فایل‌های تغییرکرده

- `AGENTS.md`: wording مربوط به roadmap evidence به handoff evidence تبدیل شد.
- `KARIZ_PROJECT_HANDOFF.md`: تنها live truth شد و scope، phase، gate، blocker، evidence و next action را ادغام کرد.
- `docs/KARIZ_CAPABILITIES_FOR_INVOICE_FA.txt`: disclaimer تحویل با `VERIFIED_END_TO_END` همسان شد.
- `docs/backend/DISCOVERY.md`: snapshot فنی از live status جدا شد.
- `docs/ops/DEPLOYMENT.md`: procedure snapshot از live proof state جدا شد.
- `docs/ops/DEPENDENCIES.md`: dependency evidence به‌عنوان snapshot تاریخ‌دار مشخص شد.
- `docs/ops/RELEASE_NOTES.md`: release snapshot از current state جدا شد.
- `docs/ops/SOURCE_MANIFEST.md`: manifest تاریخی از current path/status جدا شد.
- `KARIZ_PRODUCT_COMPLETION_ROADMAP.md`: پس از ادغام حذف شد.
- `docs/KARIZ_FUTURE_BACKEND_WORK_FA.md`: پس از ادغام حذف شد.

### migration، endpoint و authorization

- migration: ندارد.
- endpoint: ندارد.
- authorization behavior: تغییر ندارد.

### تست این مرحله

- `MARKDOWN_LINKS_PASS`: 28 سند root/`docs`؛ link نسبی شکسته پیدا نشد.
- `DELETED_REFS_PASS`: reference فعال به دو سند حذف‌شده پیدا نشد؛ نام آن‌ها فقط در سابقه ادغام همین فایل مانده است.
- `REQUIRED_DOCS_PASS`: هر 9 سند الزامی نگه‌داشته‌شده موجود است.
- `ROOT_DUPLICATE_STATUS_PASS`: سند duplicate root برای status/roadmap/worklog/blocker/readiness پیدا نشد.
- `LIVE_STATUS_OWNERSHIP_PASS`: 5 سند discovery/release/dependency/deployment/manifest صریحا snapshot یا procedure شدند، نه live status.
- `git diff --check`: پاس.
- `HANDOFF_CONTRACT_PASS`: 16 بخش/عبارت اجباری حاضر است.
- `INVOICE_DISCLAIMER_PASS`: backend/HTML به‌تنهایی تحویل نیست و فقط `VERIFIED_END_TO_END` پذیرفته است.
- self-correction score: `9/10`؛ merge، ownership، reference، link، scope و acceptance contract بدون defect باز این مرحله پاس شد.

## 14. evidence پاک‌سازی HTML و branding

### نتیجه

- وضعیت slice: complete در repository؛ browser/runtime proof هنوز external است و هیچ capability به `VERIFIED_END_TO_END` ارتقا نیافت.
- 205 فایل HTML tracked اسکن شد: 202 فایل first-party در scope و 3 فایل third-party IcoMoon زیر `src/plugins/keenicons/` خارج از تغییر و دست‌نخورده ماند.
- header/license comment بالای 201 فایل archive حذف شد؛ فایل home از قبل آن header را نداشت.
- هر 202 فایل first-party دارای `lang="fa"`، `dir="rtl"`، title فارسی با suffix برابر `| Kariz CRM` و robots برابر `noindex,nofollow,noarchive` است.
- vendor title/description/keywords، OG URL/site branding قدیمی، canonical جعلی، `landing.html` link، purchase/demo/support/social link و vendor credit حذف شد.
- نام محصول در metadata فعال برابر `Kariz CRM | کاریز` و description برابر `سامانه مدیریت ارتباط با مشتری کاریز` است.
- URL بیرونی غیرمجاز صفر است؛ فقط Google Fonts، amCharts CDN و namespace استاندارد W3C به‌عنوان technical asset contract باقی ماند.
- شمار `data-kt-*` قبل و بعد برابر 69339 و شمار `assets/plugins/` برابر 819 ماند؛ KT contract یا plugin path rename نشد.
- فایل minified/bundle JavaScript/CSS، binary/logo/favicon، `LICENSE*`، `NOTICE*` و third-party attribution تغییر نکرد.

### فایل‌های تغییرکرده این slice

- 202 فایل HTML first-party tracked: همه `*.html`های repository به‌جز سه مسیر `src/plugins/keenicons/*/demo.html`.
- `common/templates/common/home.html`: title و robots داخلی.
- `scripts/check_html_branding.py`: normalizer bounded و regression scan fail-closed.
- `common/tests/test_html_branding.py`: اجرای scan در Django suite.
- `common/tests/test_ui.py`: assertion عنوان فارسی و robots.
- `KARIZ_PROJECT_HANDOFF.md`: status، evidence، tests و next action.

### migration، endpoint و authorization

- migration: ندارد.
- endpoint: ندارد.
- authorization behavior: تغییر ندارد.

### تست‌های این slice

- `python scripts/check_html_branding.py`: پاس؛ `HTML_BRANDING_PASS files=202`.
- `python manage.py check --settings=config.test_settings`: پاس؛ 0 issue.
- `python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0`: پاس.
- `python manage.py test common.tests.test_ui common.tests.test_html_branding --settings=config.test_settings -v 2`: پاس؛ 5 تست.
- `python manage.py makemigrations --check --dry-run --settings=config.test_settings`: پاس؛ no changes.
- `python manage.py test --settings=config.test_settings -v 1`: پاس؛ 233 تست، 6 PostgreSQL-only skip.
- `git diff --check`: پاس.
- technical-contract gate: پاس؛ `data-kt=69339`، `plugin_paths=819`، external غیرمجاز 0، protected change صفر.
- self-correction score: `9/10`؛ false-positive دامنه `x.com`، support/demo linkهای باقی‌مانده و trailing whitespace در loop اصلاح و همه gateها دوباره پاس شد.

### blocker باقی‌مانده

- browser desktop/mobile، console/network و served-archive proof روی runtime واقعی هنوز در `EXT-006` باز است.
- archive همچنان طبق `docs/backend/DISCOVERY.md` توسط Django serve نمی‌شود؛ پاک‌سازی آن ادعای قابلیت end-user نیست.

## 15. evidence پوسته auth و مدیریت کاربر

### نتیجه و وضعیت قابلیت

- auth/user shell در repository کامل است: login با username/password، logout، me/profile، user list/detail/create/edit/deactivate و change-role کنترل‌شده به Session Authentication + CSRF واقعی وصل است.
- roleها فقط `sales_agent`، `sales_manager`، `company_it` و `platform_admin` هستند؛ create/edit هیچ role یا server-owned field پنهان ارسال نمی‌کند و تغییر role فقط endpoint اختصاصی را می‌زند.
- inactive session پاک و رد می‌شود؛ queryset/object authorization backend، جداسازی CRM role از server access و last-active-platform-admin guard تغییر نکرد.
- رابط فقط routeهای واقعی `/login/`، `/`، `/users/` و `/users/<id>/` را نشان می‌دهد؛ public sign-up، generic role builder، file redirect، `action="#"`، fake success و dead module ندارد.
- loading، empty، validation، 403، 404، 409، 429، network و generic error فارسی پیاده شد؛ success فقط پس از پاسخ موفق API نشان داده می‌شود.
- desktop two-column و mobile drawer responsive در headless Chrome تست شد؛ Persian/RTL DOM، console و same-origin response status نیز بررسی شد.
- capability state: `IN_PROGRESS`؛ repository و browser محلی پاس است ولی native PostgreSQL و release-target browser/runtime proof باز است، پس `VERIFIED_END_TO_END` نیست.

### فایل‌های تغییرکرده این slice

- `common/ui_views.py` و `common/ui_urls.py`: route و guard فعال CRM، scope مدیریت کاربر و 403/404 امن.
- `common/error_views.py` و `common/templates/common/error.html`: صفحه‌های خطای فارسی و امن برای UI.
- `common/templates/common/base.html`، `login.html`، `home.html`، `users/list.html` و `users/detail.html`: shell فارسی RTL نگهداری‌شده و فرم‌های واقعی.
- `common/static/common/kariz.css` و `common/static/common/kariz-app.js`: responsive shell، fetch same-origin، CSRF، state و flowهای auth/user.
- `config/settings.py`: مسیر static نام‌دار فقط برای logo/favicon موجود repository.
- `common/tests/test_auth_shell.py`: unit، API و browser-contract desktop/mobile.
- `common/tests/test_auth_shell_browser.py`: Selenium live-server flow واقعی desktop/mobile، Persian/RTL، console/network status و skip صریح در نبود browser driver.
- `common/tests/test_ui.py`: home محافظت‌شده و brand contract.
- `scripts/check_html_branding.py`: templateهای Django ارث‌بر را به‌عنوان fragment اسکن می‌کند و سند پایه را مرجع metadata می‌داند.
- `KARIZ_PROJECT_HANDOFF.md`: phase، status، evidence، blocker و resume point جاری.

### migration، endpoint و authorization

- migration: ندارد.
- API endpoint تازه: ندارد؛ endpointهای موجود auth/users مصرف شدند.
- UI endpoint تازه: `/login/`، `/users/` و `/users/<int:user_id>/`؛ `/` از public brand page به profile shell محافظت‌شده تبدیل شد.
- authorization: backend تغییر نکرد؛ UI همان active CRM identity و admin role boundary را پیش از render اعمال می‌کند. مدیر فنی مشتری، مدیر پلتفرم را نمی‌بیند و نمی‌تواند آن نقش را بدهد یا مدیریت کند.

### تست‌های این slice

- `python manage.py test common.tests.test_auth_shell common.tests.test_ui accounts.tests.test_accounts --settings=config.test_settings`: پاس؛ 41 تست.
- `python manage.py check --settings=config.test_settings`: پاس؛ 0 issue.
- `python manage.py makemigrations --check --dry-run --settings=config.test_settings`: پاس؛ no changes.
- `node --check common/static/common/kariz-app.js`: پاس.
- `python scripts/check_html_branding.py`: پاس؛ 207 فایل HTML/template first-party.
- `python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0`: پاس.
- `python manage.py test --settings=config.test_settings -v 1`: پاس؛ 248 تست، 6 PostgreSQL-only skip؛ دو تست headless Chrome اجرا شد.
- `python manage.py test common.tests.test_auth_shell_browser --settings=config.test_settings -v 2`: پاس؛ 2 headless Chrome test برای desktop login/profile/logout و mobile nav/user-list.
- `git diff --check`: پاس.
- browser محلی اجرا شد؛ release-target browser/edge/TLS proof در `EXT-006` باز می‌ماند.

### self-correction loop

- score نخست: `8/10`.
- [common/templates/common/error.html]: title پویا scan را شکست. gate fail شد.
- fix: title امن فارسی ثابت شد؛ inherited-template scan از document metadata جدا شد.
- score دوم: `8/10`.
- [active shell favicon]: favicon route نبود. Browser console و network خطای 404 داد.
- fix: favicon موجود `assets/media/logos/favicon.ico` با static prefix محدود وصل شد و browser gate تکرار شد.
- score سوم: `8/10`.
- [common/tests/test_ui.py]: global finder cache از test دیگر اثر گرفت. Full suite fail شد.
- fix: asset source و URL render مستقیم سنجیده شد؛ browser test همچنان served favicon را ثابت می‌کند.
- score نهایی: `9/10`؛ shell/auth/user contract و gateهای repository defect باز ندارند.

### blocker باقی‌مانده

- `EXT-001`: PostgreSQL native migration/constraint/concurrency proof.
- `EXT-006`: تکرار browser desktop/mobile و console/network/visual proof روی release target پشت edge/TLS.
- سایر blockerهای deploy در بخش 11 برای production claim باز هستند.

## 16. evidence رابط Customer، CustomerPhone، Lead و Interaction

### نتیجه و وضعیت قابلیت

- Customer list/detail/create/edit/search/order/pagination و deactivate بدون hard delete به API واقعی وصل شد؛ `created_by` و `is_active` در فرم قابل ارسال نیست.
- CustomerPhone داخل جزئیات مشتری list/create/edit/deactivate واقعی دارد؛ `customer` در edit قابل تغییر نیست، `normalized_phone` و `is_active` server-owned هستند، deactivate اختصاصی row/history را نگه می‌دارد و primary را پاک می‌کند.
- ورودی فارسی/عربی/ASCII تلفن به `+98` ASCII نرمال می‌شود؛ duplicate active و primary conflict با HTTP 409 نمایش داده می‌شود و 429 واقعی برای deactivate تست شد.
- Lead list/detail/create/edit مجاز/search/order/pagination و status filter exact دارد. وضعیت فقط نمایش/filter می‌شود؛ هیچ transition، status list، Team boundary یا auto-assignment ساخته نشد.
- assignee read API فقط حداقل فیلد active clean Sales Agent را به سه role مجاز می‌دهد؛ تخصیص/انتقال همچنان service تراکنشی موجود را می‌زند و history paginated از scope همان Lead خوانده می‌شود.
- Sales Agent سرنخ ساخته‌شده ولی تخصیص‌نیافته را فقط می‌بیند و edit control غیرفعال است؛ پس از تخصیص edit و Interaction مجاز می‌شود. سه role بالاتر company-wide behavior موجود را دارند و Team حدس زده نشد.
- Interaction list/detail/create/search/order/pagination به API append-only وصل است؛ فقط direction تاییدشده `inbound`/`outbound` انتخاب می‌شود و outcome همان متن bounded است، نه code حدسی.
- همه صفحه‌ها فارسی/RTL و دارای loading، empty، validation، permission، not-found، conflict، throttle، network و generic error هستند؛ success فقط پس از پاسخ موفق API نشان داده می‌شود.
- capability state: `IN_PROGRESS`؛ repository و headless Chrome محلی پاس است. PostgreSQL native و release-target browser/edge/TLS هنوز external است، پس `VERIFIED_END_TO_END` نیست.

### فایل‌های بررسی‌شده

- `AGENTS.md`، `BACKEND_SPEC.md`، `KARIZ_PROJECT_HANDOFF.md`، `manage.py`، `config/urls.py` و تنظیمات DRF.
- `accounts/access.py`، model/permission/serializer/view نقش‌ها.
- `sales/models.py`، `selectors.py`، `serializers.py`، `services.py`، `views.py`، `urls.py` و تست‌های workflow/scope.
- `common/viewsets.py`، error/phone/throttle contract، route/view/template/CSS/JavaScript فعال و تست‌های auth/browser/schema.
- `docs/backend/API_CONTRACT.md`.

### فایل‌های تغییرکرده این slice

- `common/ui_views.py` و `common/ui_urls.py`: route محافظت‌شده و direct-ID scope برای Customer، Lead و Interaction؛ edit guard سرنخ تخصیص‌نیافته.
- `common/templates/common/base.html` و templateهای تازه `customers/`، `leads/` و `interactions/`: navigation و فرم/جدول واقعی فارسی.
- `common/static/common/kariz-app.js` و `kariz.css`: same-origin/CSRF client، list/detail/create/edit/deactivate/reassign/history/call flows، state و responsive layout.
- `common/viewsets.py`: query parameterهای strict برای actionهای paginated.
- `sales/serializers.py`، `services.py` و `views.py`: display fieldهای read-only، phone filter/deactivate، assignee و assignment-history API و scope دقیق Interaction create.
- `docs/backend/API_CONTRACT.md`: قرارداد endpoint/filter/throttle تازه.
- `common/tests/test_sales_shell.py`، `test_sales_shell_browser.py` و `test_system_api.py`: unit/API/role/direct-ID/schema/headless browser proof.
- `KARIZ_PROJECT_HANDOFF.md`: phase، evidence، blocker و resume point.

### migration، endpoint و authorization

- migration: ندارد؛ schema drift صفر.
- UI endpoint تازه: `/customers/`، `/customers/<int:customer_id>/`، `/leads/`، `/leads/<int:lead_id>/`، `/interactions/` و `/interactions/<int:interaction_id>/`.
- API endpoint تازه: `POST /api/v1/customer-phones/{id}/deactivate/`، `GET /api/v1/leads/assignees/` و `GET /api/v1/leads/{id}/assignment-history/`؛ `GET customer-phones/` فیلتر exact `customer` گرفت.
- authorization: Sales Agent فقط Customer خود/assigned، Lead assigned یا own-unassigned برای view، فقط assigned برای Lead edit/Interaction و بدون deactivate Customer/reassign است؛ Sales Manager، Company IT و Platform Admin scope عملیاتی company-wide موجود را دارند. direct-ID و custom-action خارج scope برای agent برابر 404 است.
- server-owned: customer identity در Lead edit، Customer/agent در Interaction، owner/assignment/status/source payload، normalized/active phone و همه timestampها قابل mass assignment نیستند.

### تست‌های این slice

- `python manage.py test --settings=config.test_settings -v 1`: پاس؛ 263 تست، 6 PostgreSQL-only skip؛ 3 headless Chrome test پاس.
- `python manage.py test common.tests.test_sales_shell_browser --settings=config.test_settings -v 1`: پاس؛ Customer create/detail/phone، Lead create/reassign/history، Interaction create/detail و Customer deactivate در Chrome واقعی محلی.
- `python manage.py test common.tests.test_system_api common.tests.test_sales_shell --settings=config.test_settings -v 1`: پاس؛ 28 تست.
- `python manage.py check --settings=config.test_settings`: پاس؛ 0 issue.
- `python manage.py makemigrations --check --dry-run --settings=config.test_settings`: پاس؛ no changes.
- `python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0`: پاس.
- `node --check common/static/common/kariz-app.js`: پاس.
- `python scripts/check_html_branding.py`: پاس؛ `HTML_BRANDING_PASS files=213`.
- `git diff --check`: پاس.

### self-correction loop

- score نخست: `8/10`.
- [browser test gate]: اجرای موازی timeout شد. proof گم شد.
- fix: gateها مستقل و browser flow واقعی افزوده شد.
- score دوم: `8/10`.
- [lead detail]: کارشناس برای Lead تخصیص‌نیافته edit مرده می‌دید. API رد می‌کرد.
- [lead product]: محصول inactive پنهان با edit یادداشت ممکن بود پاک شود. data drift می‌شد.
- fix: edit browser با assignment scope قفل شد و شناسه محصول تاریخی بدون افشای نام حفظ شد.
- score سوم: `8/10`.
- [real browser test]: درخواست‌های موازی روی SQLite shared test connection خطای گذرا داد. full suite fail شد.
- fix: بارگیری‌های وابسته UI ترتیبی شد؛ browser مستقل و full suite دوباره پاس شد.
- score نهایی: `9/10`؛ defect repository-controlled باز در این slice نیست.

### blocker باقی‌مانده

- `EXT-001`: migration/constraint/concurrency روی PostgreSQL native.
- `EXT-006`: تکرار desktop/mobile و console/network/visual proof روی release target پشت edge/TLS.
- blockerهای deploy دیگر بخش 11 برای production claim باز هستند.

## 17. evidence رابط Product، Sale، report و audit

### نتیجه و وضعیت قابلیت

- Product list/detail/create/edit/search/order/pagination/deactivate به API واقعی وصل شد. Sales Agent فقط Product فعال را می‌خواند و هیچ create/edit/deactivate control ندارد؛ سه role بالاتر مدیریت می‌کنند و سوابق با deactivate نگه داشته می‌شود.
- Sale list/detail/create/search/order/status filter و cancel کنترل‌شده وصل شد. فرم فروش فقط Lead مجاز، Product فعال، quantity و notes می‌فرستد؛ Customer، seller، snapshot قیمت، total، status و timestamp را server تعیین می‌کند. correction و hard delete اضافه نشد.
- Sales Agent فقط از Lead تخصیص‌یافته فروش می‌سازد و serializer هم relation خارج scope را قبل از service پنهان می‌کند. direct-ID Product غیرفعال و Sale دیگران در browser و API برای Agent برابر 404 است؛ سه role بالاتر company-wide behavior موجود را دارند.
- گزارش user-performance با یک query مشترک JSON و XLSX اجرا می‌شود؛ همان period/user/product filter برای هر دو format استفاده می‌شود و metricها همان چهار metric قرارداد هستند. formula-injection defense موجود حفظ و دوباره تست شد.
- ActivityLog list/detail/search/order/pagination کاملا read-only است. Company IT و Platform Admin همان selector API را در browser دارند؛ Sales Agent و Sales Manager برابر 403 و direct-ID پنهان Company IT برابر 404 است.
- صفحه‌ها stateهای loading، empty، validation، permission، not-found، conflict، throttle، network و generic error دارند. Chrome واقعی create/edit Product، create/cancel Sale، JSON report، XLSX fetch و ActivityLog list/detail را بدون console/network error اجرا کرد.
- capability state: `IN_PROGRESS`؛ V3 repository و headless Chrome محلی پاس است. PostgreSQL native و release-target browser/edge/TLS هنوز external است، پس `VERIFIED_END_TO_END` یا production-ready ادعا نمی‌شود.

### فایل‌های بررسی‌شده

- `AGENTS.md`، `BACKEND_SPEC.md`، `KARIZ_PROJECT_HANDOFF.md` و `docs/backend/API_CONTRACT.md`.
- `sales/models.py`، `selectors.py`، `serializers.py`، `services.py`، `views.py` و `urls.py`.
- `reports/serializers.py`، `services.py`، `views.py`، `xlsx.py`، `urls.py` و تست‌های user-performance.
- `auditlog/models.py`، `permissions.py`، `selectors.py`، `serializers.py`، `views.py`، `urls.py` و تست‌های scope/read-only.
- `common/ui_views.py`، `ui_urls.py`، template/CSS/JavaScript فعال و تست‌های shell/browser/system.

### فایل‌های تغییرکرده این slice

- `sales/serializers.py`: display fieldهای read-only Product/Sale و relation دقیق Lead تخصیص‌یافته برای Sale Agent.
- `common/ui_views.py` و `common/ui_urls.py`: route، role guard و direct-ID scope برای Product، Sale، report و ActivityLog.
- `common/templates/common/base.html` و templateهای تازه `products/`، `sales/`، `reports/` و `activity_logs/`: navigation و flow فارسی/RTL واقعی.
- `common/static/common/kariz-app.js` و `kariz.css`: Product/Sale/report/XLSX/audit flow و stateها.
- `docs/backend/API_CONTRACT.md`: قرارداد browser route و server-owned Sale fields.
- `common/tests/test_commercial_shell.py` و `test_sales_shell_browser.py`: contract، role، object scope، CSRF، conflict، cancel، parity/XLSX و Chrome proof.
- `KARIZ_PROJECT_HANDOFF.md`: V3، evidence، blocker و resume point.

### migration، endpoint و authorization

- migration: ندارد؛ schema drift صفر.
- UI endpoint تازه: `/products/`، `/products/<int:product_id>/`، `/sales/`، `/sales/<int:sale_id>/`، `/reports/user-performance/`، `/activity-logs/` و `/activity-logs/<int:activity_log_id>/`.
- API endpoint تازه ندارد؛ UI فقط endpointهای versioned موجود Product، Sale، report/export و ActivityLog را مصرف می‌کند.
- Product read برای چهار role است؛ Sales Agent فقط active و read-only، سه role بالاتر create/update/deactivate. Sale Agent فقط Sale خود و Lead تخصیص‌یافته؛ سه role بالاتر Saleهای company-wide موجود. cancel فقط Sales Manager، Company IT و Platform Admin. ActivityLog فقط Company IT و Platform Admin با selector موجود.
- server-owned: browser هیچ input یا payload برای snapshot قیمت، total، Customer، seller، Sale status/time، audit actor یا timestamp ندارد. ارسال total جعلی همراه Product در API نیز نتیجه را عوض نمی‌کند و service total را از snapshot قیمت ضربدر quantity می‌سازد.

### تست‌های این slice

- `python manage.py test --settings=config.test_settings -v 1`: پاس؛ 274 تست، 6 PostgreSQL-only skip؛ 4 headless Chrome test پاس.
- `python manage.py test common.tests.test_commercial_shell common.tests.test_sales_shell common.tests.test_system_api sales.tests.test_workflows sales.tests.test_scope_attacks reports.tests.test_user_performance auditlog.tests.test_api --settings=config.test_settings -v 1`: پاس؛ 101 تست.
- `python manage.py test common.tests.test_sales_shell_browser --settings=config.test_settings -v 2`: پاس؛ 2 Chrome test شامل Product/Sale/report/XLSX/audit و Customer/Lead/Interaction.
- `python manage.py check --settings=config.test_settings`: پاس؛ 0 issue.
- `python manage.py makemigrations --check --dry-run --settings=config.test_settings`: پاس؛ no changes.
- `python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0`: پاس.
- `node --check common/static/common/kariz-app.js`: پاس.
- `python scripts/check_html_branding.py`: پاس؛ `HTML_BRANDING_PASS files=220`.
- `git diff --check`: پاس.

### self-correction loop

- score نخست: `8/10`.
- [report error state]: خطای report loading را باز می‌گذاشت. کاربر state دروغ می‌دید.
- [direct Product scope test]: browser proof بود ولی API direct-ID ماتریس چهار role کامل نبود. regression ممکن بود پنهان بماند.
- fix: loading در finally بسته شد و Product/Sale direct-ID همزمان در browser و API برای هر چهار role تست شد.
- score نهایی: `9/10`؛ defect repository-controlled باز در این slice نیست.

### blocker باقی‌مانده

- `EXT-001`: migration/constraint/concurrency روی PostgreSQL native.
- `EXT-002` تا `EXT-007`: secret، backup/restore، static/TLS edge، rate/concurrency، release-target browser و operator evidence طبق بخش 11.
- claim فعلی: `production candidate; external verification pending`.

## 18. اقدام قبلی پیش از Client-1 — superseded

این اقدام دیگر resume point زنده نیست. V4 safe frontend cleanup و Persian/branding فقط پس از قراردادها و ترتیب Client-1 در بخش 20 اجرا می‌شود؛ از این بخش شروع نکن.

resume point زنده فقط در آخرین checkpoint بخش 20 است.

## 19. Client-1 C1-0 live checkpoint

### Checkpoint C1-0.1 - authority and baseline identity

- Active phase: `C1-0` only.
- Current task/subtask: required authority/roadmap read and baseline Git identity capture; next task is bounded contract/document inspection.
- Files inspected: `AGENTS.md`, `BACKEND_SPEC.md`, `KARIZ_PROJECT_HANDOFF.md`, and the root Client-1 step-by-step roadmap.
- Files changed: `KARIZ_PROJECT_HANDOFF.md` only.
- Migrations: none expected; none created or changed.
- API endpoints changed: none.
- UI routes changed: none.
- Authorization impact: none.
- Exact commands executed:
  - `git rev-parse HEAD` -> PASS, exit 0, `d5c120c1154b00fbd584fc0133aaaa96335eb3b4`.
  - `git status --short` -> PASS, exit 0, clean output before this handoff edit.
- Assumptions: the seven initial Client-1 items are intake text only; no item is an implementation contract.
- Provisional requirements: pending the C1-0 contract mapping checkpoint; all seven will remain `PROVISIONAL` and `BLOCKED_DECISION`.
- Unresolved decisions: all domain meanings, workflows, formulas, statuses, roles/workstreams, sources, date bases, filters, exports, and acceptance rules named by C1-0 remain unresolved.
- Blockers: the customer's final detailed requirement source is unavailable; this blocks C1-1 and all functional Client-1 work, but does not block C1-0 documentation or repository verification.
- Current Git commit: `d5c120c1154b00fbd584fc0133aaaa96335eb3b4`.
- Current git status: clean before this handoff edit; after the edit, `KARIZ_PROJECT_HANDOFF.md` is expected modified.
- Exact resume point: inspect `docs/backend/API_CONTRACT.md`, `docs/backend/ENTITY_CATALOG.md`, `docs/backend/RELATIONSHIPS.md`, `docs/backend/ERD.mmd` when present, and only verification-relevant `docs/ops` files.
- Exact next action: complete the bounded current-capability mapping, then immediately update this section with all seven provisional requirements and the customer decision checklist.

### Checkpoint C1-0.2 - bounded contract inspection and provisional intake

- Active phase: `C1-0` only.
- Current task/subtask: required backend/operations contract inspection complete; seven-item provisional intake and decision checklist recorded below.
- Files inspected: `docs/backend/API_CONTRACT.md`, `docs/backend/ENTITY_CATALOG.md`, `docs/backend/RELATIONSHIPS.md`, `docs/backend/ERD.mmd`, `docs/ops/DEPENDENCIES.md`, and `docs/ops/RELEASE_CHECKLIST.md`. The two operations files were the only operations documents needed to interpret the requested repository gates and their evidence limits.
- Files changed: `KARIZ_PROJECT_HANDOFF.md` only.
- Migrations: none expected; none created or changed.
- API endpoints changed: none.
- UI routes changed: none.
- Authorization impact: none.
- Exact commands executed for this subtask:
  - `Get-Content -LiteralPath AGENTS.md -Raw`
  - `Get-Content -LiteralPath BACKEND_SPEC.md -Raw`, followed by bounded reads of lines 1-190, 191-380, 381-570, and 571-762 after combined output truncation.
  - `Get-Content -LiteralPath KARIZ_PROJECT_HANDOFF.md -Raw`, followed by bounded reads of lines 1-180, 181-360, and 361-528 after combined output truncation.
  - bounded full read of the root Client-1 step-by-step roadmap in lines 1-220, 221-440, 441-660, 661-880, and 881-1013 after combined output truncation.
  - `Get-Content -LiteralPath docs/backend/API_CONTRACT.md -Raw`
  - `Get-Content -LiteralPath docs/backend/ENTITY_CATALOG.md -Raw`
  - `Get-Content -LiteralPath docs/backend/RELATIONSHIPS.md -Raw`
  - `Get-Content -LiteralPath docs/backend/ERD.mmd -Raw`
  - `Get-Content -LiteralPath docs/ops/DEPENDENCIES.md -Raw`
  - `Get-Content -LiteralPath docs/ops/RELEASE_CHECKLIST.md -Raw`
  - `git status --short` -> PASS, exit 0, output ` M KARIZ_PROJECT_HANDOFF.md`.
- Assumptions: none of the source phrases below defines a model, enum, formula, date field, workflow, role/workstream, provider contract, legal meaning, or acceptance test. Existing repository behavior is only the closest comparison point.
- Blocker: the final detailed customer source is missing. All seven items stay `PROVISIONAL` and `BLOCKED_DECISION`; C1-1 and every functional implementation phase remain blocked.
- Current Git commit: `d5c120c1154b00fbd584fc0133aaaa96335eb3b4`.
- Current git status: ` M KARIZ_PROJECT_HANDOFF.md`.
- Exact resume point: run the C1-0 repository verification gates in the specified order, record the exact result of each gate immediately, then inspect the final diff for no-code/no-contract-promotion scope.
- Exact next action: run `python manage.py check --settings=config.test_settings`.

#### Client-1 initial requirements - provisional intake only

Every entry in this subsection comes from the initial customer list. Each is `PROVISIONAL` and `BLOCKED_DECISION`. None is an implementation contract. No wording below approves a business entity, status, formula, workflow, role, route, or data source.

##### C1-REQ-001

- Status: `PROVISIONAL`; `BLOCKED_DECISION`.
- Source authority: initial customer list only; not yet an implementation contract.
- Source wording: Sales panel with no software-enforced account/seat limit.
- Closest existing repository capability: fixed-role CRM User administration plus the maintained sales shell over Customer, CustomerPhone, Lead, assignment history, Interaction, Product, Sale, user-performance report, and audit. Current contracts document no application seat-count field or licensing gate; this does not prove unlimited concurrency or target capacity.
- Exact missing business decisions: confirm that "unlimited users" means no application seat cap; expected total and peak concurrent users; approved capacity/load target and abort rule; exact sales user types or workstreams; manager/team boundary; account create/reactivate/deactivate rules; cross-panel access; which sales pages and actions form the panel; target deployment profile and acceptance cases.

##### C1-REQ-002

- Status: `PROVISIONAL`; `BLOCKED_DECISION`.
- Source authority: initial customer list only; not yet an implementation contract.
- Source wording: After-sales panel with no software-enforced account/seat limit.
- Closest existing repository capability: current User lifecycle and fixed roles can authenticate clean CRM identities, while `AfterSalesRequest` is only optional schema-compatible scope in `BACKEND_SPEC.md`; no after-sales entity, API, UI route, workstream, or authorization contract exists.
- Exact missing business decisions: confirm no application seat cap separately from concurrency; define after-sales user identity/workstream and manager boundary; cross-panel visibility for all four roles; case creator and eligible assignee; required fields; Customer and Sale/document relation; statuses and allowed transitions; reassignment, close/reopen, lifecycle, audit, visibility, filters, pages, errors, data retention, and acceptance cases.

##### C1-REQ-003

- Status: `PROVISIONAL`; `BLOCKED_DECISION`.
- Source authority: initial customer list only; not yet an implementation contract.
- Source wording: Management panel showing detailed user performance and drill-down.
- Closest existing repository capability: existing `/api/v1/reports/user-performance/`, XLSX export, and `/reports/user-performance/` UI provide scoped rows for `customers_created_count`, `sales_count`, `sales_amount`, and `average_sale_amount`; no approved detailed drill-down contract exists.
- Exact missing business decisions: exact management users and object scope; every metric numerator, denominator, inclusion/cancellation rule, source timestamp, reassignment-history rule, timezone, calendar, date boundary, filters, grouping, sort, pagination/bounds, drill-down row types and fields, detail access, JSON/XLSX/UI parity, Persian labels/format, empty/zero rules, sample expected totals, and acceptance cases.

##### C1-REQ-004

- Status: `PROVISIONAL`; `BLOCKED_DECISION`.
- Source authority: initial customer list only; not yet an implementation contract.
- Source wording: Inbound SMS count report grouped by day and hour.
- Closest existing repository capability: CustomerPhone normalization and manual Interaction direction `inbound` exist, but Interaction is not an SMS record. No inbound SMS entity, provider adapter, webhook/polling route, stored message contract, or SMS report exists.
- Exact missing business decisions: provider and official documentation; webhook versus polling; authentication/signature; replay window; provider message/idempotency key; sender/recipient meaning and normalization; retained fields and metadata bounds; whether message body may be stored, retention and access; authoritative received timestamp; timezone and day/hour boundary; Jalali/Gregorian display; counted unit and duplicate rule; filters; report roles/scope; backfill/import; error handling; sample payloads stripped of private data; acceptance cases.

##### C1-REQ-005

- Status: `PROVISIONAL`; `BLOCKED_DECISION`.
- Source authority: initial customer list only; not yet an implementation contract.
- Source wording: Invoice/sales-document count report grouped by city and province.
- Closest existing repository capability: Customer has optional current province/city and Sale is an operational success record with Customer/product/price snapshots. Sale is explicitly not a legal/accounting Invoice. No Invoice entity, sales-document contract, geography snapshot, or province/city count report exists.
- Exact missing business decisions: whether the counted object is existing Sale, a new internal order/document, or legal/accounting invoice; source of truth; relationship and cardinality with Sale/Lead/Customer/Product; line items; numbering; amount/rounding/tax only if required; create/import source; cancellation/correction; counted statuses; report date field and half-open boundaries; province/city vocabulary and source; required/null/unknown handling; historical snapshot versus current Customer address; city-to-province validity; deduplication; filters; access; export; sample expected result and acceptance cases.

##### C1-REQ-006

- Status: `PROVISIONAL`; `BLOCKED_DECISION`.
- Source authority: initial customer list only; not yet an implementation contract.
- Source wording: Incoming-number report grouped by contact status.
- Closest existing repository capability: CustomerPhone stores normalized phone identity, Lead stores an opportunity, and Interaction stores manual inbound/outbound contact with bounded free-text outcome. None is approved as "incoming number" or "contact status", and no such grouped report exists.
- Exact missing business decisions: counted unit among Lead, unique phone, call, SMS sender, imported row, or another source; ingestion/source of truth; date field and period; deduplication across Customer/Lead/campaign/time; exact contact statuses; whether status is stored or derived; qualifying interactions; no-contact state; latest-interaction rule and deterministic tie-break; effect of later contact/status change; inbound/outbound inclusion; free-text legacy mapping or refusal; filters; role/object scope; drill-down/export; sample rows and acceptance totals.

##### C1-REQ-007

- Status: `PROVISIONAL`; `BLOCKED_DECISION`.
- Source authority: initial customer list only; not yet an implementation contract.
- Source wording: Registered invoice/sales-document report grouped by postal status.
- Closest existing repository capability: Sale provides an operational sales record and cancellation state, but it is not an Invoice. No postal status field, status history, tracking code, carrier/provider adapter, transition service, or postal report exists.
- Exact missing business decisions: same document meaning/source-of-truth decisions as C1-REQ-005; meaning of "registered"; exact postal status codes and labels; initial status; allowed transitions and terminal states; who may change status; manual versus carrier/provider ownership; current status versus append-only history; effective timestamp and report date basis; tracking-code format/uniqueness/privacy; cancellation, return, failed-delivery and correction behavior; status at historical report time versus current status; filters; role scope; audit; export; sample expected totals and acceptance cases.

#### C1-1 customer decision checklist

- [ ] Confirm "unlimited users" as no application seat cap, separately record expected total users, peak concurrent users, production-shaped capacity target, and safe load-test abort rule.
- [ ] Define exact sales and after-sales user types/workstreams, whether the four fixed CRM roles remain, manager/team boundaries, cross-panel access for each role, and account create/reactivate/deactivate lifecycle.
- [ ] Define "invoice/sales document" as existing Sale, new internal operational order/document, or legal/accounting Invoice; define line items, numbering, source of truth, amounts/rounding, creation/import, correction, cancellation, and required relationships.
- [ ] Define province/city source and vocabulary, required/optional/unknown behavior, city/province validation, historical snapshot versus current Customer values, and exact report date basis.
- [ ] Define every postal status and transition, initial/terminal states, actor permissions, manual versus provider integration, tracking-code rule, current/history requirement, return, failure, cancellation, and correction behavior.
- [ ] Define "incoming number" as Lead, unique normalized phone, call, SMS sender, imported row, or another unit; define source, deduplication key/window, and date basis.
- [ ] Define every contact status, stored versus derived behavior, qualifying Interaction, no-contact behavior, latest-record/tie-break rule, and treatment of existing free-text outcomes.
- [ ] Define every user-performance metric and denominator, cancelled-record and reassignment handling, timestamp/timezone/calendar, filters, drill-down source rows/fields, role visibility, output bounds, XLSX columns, and sample expected totals.
- [ ] Identify the SMS provider and official webhook/polling documents; define authentication/signature, replay and idempotency, retained fields, message-body retention/access, timezone/day/hour grouping, calendar presentation, filters, and sample requests with no credentials or private customer content.
- [ ] Provide existing-data/import needs, one redacted sales document, one redacted desired performance report, after-sales opening-to-close example, postal examples, and safe synthetic UAT cases.
- [ ] Record target server/OS, expected load, domain/DNS/TLS owner, backup destination/off-host copy/retention/RPO/RTO owner, maintenance/rollback owner, UAT users, business owner, and final acceptance sign-off owner.
- [ ] Reconcile each answer against the seven IDs, `BACKEND_SPEC.md`, current API/entity/relationship contracts, and implemented behavior; mark each result `APPROVED`, `BLOCKED_DECISION`, `BLOCKED_EXTERNAL`, or `OUT_OF_SCOPE` before any schema or feature work.

### Checkpoint C1-0.3 - repository verification in progress

- Active phase: `C1-0` only.
- Current task/subtask: required repository gates, run in roadmap order.
- Files inspected: all files recorded in C1-0.1 and C1-0.2 plus command-loaded Django settings and application modules.
- Files changed: `KARIZ_PROJECT_HANDOFF.md` only.
- Migrations: none expected; none created or changed.
- API endpoints changed: none.
- UI routes changed: none.
- Authorization impact: none.
- Verification evidence:
  - `python manage.py check --settings=config.test_settings` -> PASS, exit 0; `System check identified no issues (0 silenced)`.
  - `python manage.py makemigrations --check --dry-run --settings=config.test_settings` -> PASS, exit 0; `No changes detected`; 0 migrations created.
  - `$env:PYTHONUTF8='1'; python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings` -> PASS, exit 0; OpenAPI 3.0.3 generated and validation completed with fail-on-warn active. UTF-8 mode is the previously proven Windows console prerequisite for Persian schema output.
  - `python manage.py test --settings=config.test_settings -v 1` -> PASS, exit 0; 274 tests run in 56.634 seconds, 268 non-skipped passed, 6 PostgreSQL-only skipped, 0 failures, 0 errors. Safe transient live-server broken-pipe shutdown lines did not change `OK (skipped=6)`.
  - `python scripts/check_html_branding.py` -> PASS, exit 0; `HTML_BRANDING_PASS files=220`.
  - `python manage.py makemigrations --check --dry-run --settings=config.test_settings` -> PASS, exit 0; `No changes detected`; migrations created: 0.
  - `python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings` -> `BLOCKED_ENVIRONMENT` on first run, exit 1. Safe error summary: Windows `cp1252` stdout encoding raised `UnicodeEncodeError` while the command tried to print Persian schema text; no schema validation warning/error was reported before the output write failed. Repository state was not modified by the failed command.
  - `$env:PYTHONUTF8='1'; python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings` -> PASS, exit 0; OpenAPI 3.0.3 schema generated and validation completed with fail-on-warn active. Direct requested invocation is therefore console-blocked on this host, while the UTF-8 retry proves schema validation.
  - `python manage.py test --settings=config.test_settings -v 1` -> PASS, exit 0; 274 tests run in 76.183 seconds, 268 non-skipped passed, 6 PostgreSQL-only skipped, 0 failures, 0 errors. Local live-server shutdown emitted safe transient broken-pipe log lines; suite result remained `OK (skipped=6)`.
  - `python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0` -> PASS, exit 0; quiet output, no files written because dry-run was used.
  - `node --check common/static/common/kariz-app.js` -> PASS, exit 0; no syntax error output.
  - `python scripts/check_html_branding.py` -> PASS, exit 0; `HTML_BRANDING_PASS files=220`.
  - `git diff --check` -> PASS, exit 0; no whitespace error. Git emitted only the working-copy line-ending notice that LF will become CRLF when Git next touches `KARIZ_PROJECT_HANDOFF.md`.
  - `git diff --stat` -> PASS, exit 0; at command time: `KARIZ_PROJECT_HANDOFF.md | 156` and `1 file changed, 156 insertions(+)`; Git emitted the same non-failing LF-to-CRLF notice.
- Assumptions: none added.
- Provisional requirements and unresolved decisions: unchanged from C1-0.2; all seven remain `PROVISIONAL` and `BLOCKED_DECISION`.
- Blockers: final detailed customer source remains unavailable. Direct OpenAPI invocation remains `BLOCKED_ENVIRONMENT` by Windows `cp1252`; UTF-8 retry passed and no repository fix is required in C1-0.
- Current Git commit: `d5c120c1154b00fbd584fc0133aaaa96335eb3b4`.
- Current git status: expected ` M KARIZ_PROJECT_HANDOFF.md`; final status refresh pending.
- Exact resume point: every requested C1-0 gate has executed; final diff/scope audit and refreshed Git identity remain.
- Exact next action: inspect `git diff -- KARIZ_PROJECT_HANDOFF.md`, prove no functional/schema/route/authorization/semantic change, then refresh commit/status and write the final C1-0 checkpoint.

### Checkpoint C1-0.4 - final C1-0 handoff

- C1-0 status: `DONE`. Baseline repository truth, seven-item provisional intake, missing decisions, and tomorrow's reconciliation checklist are recorded. C1-0 stops here.
- Active phase: `C1-0` complete; no C1-1 work started.
- Current task/subtask: final diff and scope audit complete.
- Files inspected: all files in C1-0.1/C1-0.2, the complete `git diff -- KARIZ_PROJECT_HANDOFF.md`, and final Git identity/status summaries.
- Files changed: `KARIZ_PROJECT_HANDOFF.md` only.
- Migrations: none created, changed, or approved; drift gate reports no changes.
- API endpoints changed: none.
- UI routes changed: none.
- Authorization impact: none.
- Functional feature implementation: none.
- Models/schema: no change.
- Business semantics: no provisional entity, status, formula, role/workstream, report meaning, or workflow was approved or promoted.
- Exact final audit commands/results:
  - `git diff -- KARIZ_PROJECT_HANDOFF.md` -> PASS, exit 0; full diff contains documentation-only additions in this handoff file. Post-final-update `git diff --check` also PASS, exit 0, with only the non-failing LF-to-CRLF notice.
  - `git rev-parse HEAD` -> PASS, exit 0; `d5c120c1154b00fbd584fc0133aaaa96335eb3b4`.
  - `git status --short` -> PASS, exit 0; ` M KARIZ_PROJECT_HANDOFF.md`.
  - `git diff --name-status` -> PASS, exit 0; only `M KARIZ_PROJECT_HANDOFF.md`; non-failing LF-to-CRLF notice emitted.
  - Final `git diff --stat` -> PASS, exit 0; `KARIZ_PROJECT_HANDOFF.md | 199`, `1 file changed, 199 insertions(+)`. Final `git diff --numstat` -> PASS, exit 0; `199 0 KARIZ_PROJECT_HANDOFF.md`. Both emitted only the non-failing LF-to-CRLF notice.
- Exact baseline verification evidence: check PASS with 0 issues; migration drift PASS with 0 changes; direct OpenAPI command `BLOCKED_ENVIRONMENT` by Windows `cp1252` output encoding, then UTF-8 retry PASS with fail-on-warn active; Django suite PASS with 274 run, 268 non-skipped pass, 6 skip, 0 fail, 0 error; collectstatic dry-run PASS; JavaScript syntax PASS; HTML branding PASS for 220 files; diff whitespace PASS; diff stat PASS.
- All seven provisional requirements:
  - `C1-REQ-001` sales panel/no software seat cap: `PROVISIONAL`, `BLOCKED_DECISION`, initial customer list only, not an implementation contract.
  - `C1-REQ-002` after-sales panel/no software seat cap: `PROVISIONAL`, `BLOCKED_DECISION`, initial customer list only, not an implementation contract.
  - `C1-REQ-003` management performance/drill-down: `PROVISIONAL`, `BLOCKED_DECISION`, initial customer list only, not an implementation contract.
  - `C1-REQ-004` inbound SMS count by day/hour: `PROVISIONAL`, `BLOCKED_DECISION`, initial customer list only, not an implementation contract.
  - `C1-REQ-005` invoice/sales-document count by city/province: `PROVISIONAL`, `BLOCKED_DECISION`, initial customer list only, not an implementation contract.
  - `C1-REQ-006` incoming-number count by contact status: `PROVISIONAL`, `BLOCKED_DECISION`, initial customer list only, not an implementation contract.
  - `C1-REQ-007` registered invoice/sales-document count by postal status: `PROVISIONAL`, `BLOCKED_DECISION`, initial customer list only, not an implementation contract.
- Tomorrow's decision checklist: the 12-item `C1-1 customer decision checklist` in C1-0.2 is the required systematic reconciliation gate. It covers seat cap versus capacity, identity/workstreams, document meaning, geography, postal workflow, incoming-number meaning, contact status, performance formulas/drill-down, SMS provider/security/retention/time, samples/import/UAT, target operations/owners, and final per-ID disposition.
- Assumptions: only that the initial seven phrases are intake text. No business assumption is implementation-authoritative.
- Blockers:
  - `BLOCKED_DECISION`: customer's final detailed requirement source and annotations/examples are unavailable; all seven capability contracts remain blocked.
  - `BLOCKED_ENVIRONMENT`: direct OpenAPI schema output uses Windows `cp1252` on this host; Python UTF-8 mode is the exact proven local prerequisite for this output-heavy gate.
  - Existing PostgreSQL/Docker/Nginx/TLS/backup/target-browser external proof blockers remain unchanged and were not in C1-0 scope.
- Current Git commit: `d5c120c1154b00fbd584fc0133aaaa96335eb3b4`.
- Current git status: ` M KARIZ_PROJECT_HANDOFF.md`; no other tracked or untracked path is listed.
- Self-correction score: `9/10`. C1-0 architecture/code scope remains unchanged, documentation contract is complete, verification evidence is honest, and no repository-controlled C1-0 defect remains.
- Exact resume point: C1-0 is complete. Do not resume implementation from any provisional phrase.
- Exact next phase: `C1-1`.
- Exact next action: wait for the customer's final detailed requirement source and annotations/examples; once available, read them and execute C1-1 reconciliation only. **C1-1 must NOT start until that final detailed requirement source is available.**

### Checkpoint C1-1 preflight - blocked before phase start

- Status: `BLOCKED_DECISION` before C1-1 start.
- Active phase: none; C1-0 remains complete and C1-1 has not started.
- Current task/subtask: locate the customer's final detailed Client-1 requirement source required by the C1-1 gate.
- Files inspected: root filenames bounded to Client-1, customer, requirement, and Kariz matches; final C1-0 handoff tail.
- Files changed: `KARIZ_PROJECT_HANDOFF.md` only for this blocker record.
- Migrations: none.
- API endpoints changed: none.
- UI routes changed: none.
- Authorization impact: none.
- Exact commands executed:
  - `git status --short` -> PASS, exit 0, clean output before this handoff edit.
  - bounded root file-name lookup for Client-1/customer/requirement/Kariz terms -> only the root Client-1 roadmap, this handoff, `requirements-direct.txt`, and `requirements.txt`; no final customer requirement source found.
  - `git rev-parse HEAD` -> PASS, exit 0, `bc0233fe815f93aa51a775b381c3885402d2c6bf`.
  - `Get-Content -LiteralPath KARIZ_PROJECT_HANDOFF.md -Tail 90` -> PASS, exit 0; confirmed C1-0 requires the missing source before C1-1. Post-edit `git diff --check` -> PASS, exit 0, with only the non-failing LF-to-CRLF notice.
- What failed: C1-1 authority precondition. The customer's final detailed requirement source and annotations/examples are not available in the request or bounded repository root lookup.
- Repository state modified by blocker discovery: no functional, model, migration, API, UI, or authorization state changed; only this live handoff blocker entry was added.
- Assumptions: none. The initial seven provisional phrases remain non-contractual.
- Provisional requirements: C1-REQ-001 through C1-REQ-007 remain `PROVISIONAL` and `BLOCKED_DECISION`.
- Unresolved decisions: the complete C1-1 decision checklist remains unanswered.
- Blocker: `BLOCKED_DECISION` - missing final detailed customer requirement source. C1-1 reconciliation cannot safely begin.
- Current Git commit: `bc0233fe815f93aa51a775b381c3885402d2c6bf`.
- Current git status: ` M KARIZ_PROJECT_HANDOFF.md`; no other path listed.
- Self-correction score: `9/10`; fail-closed phase gate works and no business rule was invented.
- Exact resume point: C1-1 preflight, before reading or reconciling any final customer requirement.
- Exact resume action: place the customer's final detailed requirement source in the curated repository or paste it in the request, with any annotations/examples; then read it after the required authority files and execute C1-1 only.

## 20. Client-1 C1-1 live reconciliation

### Checkpoint C1-1.1 - final source received and authority read

- Status: `IN_PROGRESS`; C1-1 documentation/reconciliation only.
- Active phase: `C1-1`.
- Current task/subtask: trace the supplied final Persian customer list to stable capability IDs and separate approved scope from unresolved implementation semantics.
- Final source: the customer's Persian list supplied in the current request, sections 1 through 10 plus the final list of capabilities outside the current operational claim.
- Confirmed source-level decisions:
  - every capability family listed by the customer belongs to the requested Client-1 end target;
  - capability does not become operational merely because a template shell exists;
  - items explicitly marked for addition/later or described as low importance must be placed in the final low-priority implementation wave, not dropped;
  - Customer hard delete must remain safe deactivation;
  - Product management remains elevated-role only;
  - Sale hard deletion and unrestricted financial editing remain forbidden;
  - manual specialist call reporting is requested; telephony duration/recording/integration is not current behavior;
  - real backup schedule/destination belongs to target infrastructure proof.
- Fail-closed interpretation: target inclusion is confirmed, but undefined entities, fields, statuses, formulas, transitions, role mappings, provider rules, integrations, security policies, and acceptance examples remain `BLOCKED_DECISION` or `BLOCKED_EXTERNAL`; template labels do not fill these gaps.
- Files inspected: `AGENTS.md`, `BACKEND_SPEC.md`, `KARIZ_PROJECT_HANDOFF.md`, customer source in the current request, `docs/backend/API_CONTRACT.md`, `docs/backend/ENTITY_CATALOG.md`, `docs/backend/RELATIONSHIPS.md`, `docs/backend/ERD.mmd`, and `docs/ops/UAT.md`.
- Files changed: `KARIZ_PROJECT_HANDOFF.md` only at this checkpoint.
- Migrations: none.
- API endpoints changed: none.
- UI routes changed: none.
- Authorization impact: none; requested three-role wording conflicts with the implemented four-role security contract and is not applied until exact mapping/privilege custody is approved.
- Exact commands executed:
  - ordered UTF-8 bounded/full reads of the authority, handoff, backend contract, entity/relationship/ERD/API contracts, and UAT runbook listed above -> PASS, exit 0.
  - targeted memory lookup for prior Kariz scope/evidence -> PASS; used only to cross-check repository claims, never to override current files or customer wording.
- Assumptions: no hidden meaning assigned to checkmarks, emoji, template state symbols, invoice, order, payment, postal status, contact status, after-sales, inbound SMS, profit, abnormal activity, automation, or integration.
- Blockers discovered:
  - exact mapping from requested three Persian roles to existing `sales_agent`, `sales_manager`, `company_it`, and `platform_admin`, including custody of platform-only privileges;
  - detailed domain contracts for every new financial, inventory, document, provider, communication, automation, file, and reporting capability;
  - external provider and target-runtime evidence where named.
- Current Git commit: `bc0233fe815f93aa51a775b381c3885402d2c6bf`.
- Current git status before C1-1 source receipt: ` M KARIZ_PROJECT_HANDOFF.md` from the prior blocked-preflight record; no other path listed.
- Exact resume point: build source trace matrix for sections 1-4 first; do not edit models, migrations, APIs, UI, or authorization.
- Exact next action: reconcile identity, user, customer, lead, interaction, and follow-up requirements; update this handoff immediately after that group.

### Checkpoint C1-1.2 - source sections 1 through 4 reconciled

#### Stable capability IDs

##### C1-CAP-ACC - accounts, identity, sessions, and user administration

- Source wording: section 1, items 1.1-1.6, plus the requested Persian role labels and template-role redesign note.
- Approved normalized wording: keep current session login/logout/me, clean active CRM identity, safe user create/search/edit/deactivate, server-controlled role changes, and backend data scoping. Session inventory/revocation, avatar, user notifications, and user-list export are included target additions but await detailed contracts.
- Business owner: `BLOCKED_DECISION`; customer owner/sign-off identity not named.
- Target users/roles/workstreams: Sales Expert and Sales Manager labels are clear; requested System Manager mapping is unclear because the same source says both four fixed roles and three fixed roles, while repository security separates `company_it` and `platform_admin`.
- Trigger/input: existing username/password/session and approved admin forms; new session/avatar/notification/export inputs unresolved.
- Stored data/source of truth: existing User plus Django session for current behavior; no avatar, notification, or approved session-management entity/storage contract exists.
- Allowed transitions: existing audited profile/account/role/deactivate transitions stay; session revoke scope and three-role migration/privilege transitions unresolved.
- Filters/date/time: existing user search/order/page stay; session age/last activity/device/IP semantics and export columns unresolved.
- UI/API contract level: existing `/login/`, `/`, `/users/`, user detail, and `/api/v1/auth/*`/`users/*` stay. No new route shape approved.
- Authorization/object scope: existing backend scope stays. Three-role mapping, team boundary, who may manage System Manager, and custody of bootstrap/audit/server-only privileges remain blocked.
- Audit: existing safe profile/account/role/deactivate audit stays; session revoke and export audit policy unresolved.
- Migration/data import impact: none for approved carry-forward; possible User role migration, session metadata, avatar storage, and notification data are blocked pending decisions.
- Acceptance examples: current login/logout/inactive/role/direct-ID cases carry forward; need three-role matrix, last-admin recovery, own/all-session revoke, avatar file limits, notification lifecycle, and export-scope examples.
- Dependencies: exact role decision before any C1-2 identity implementation; file policy before avatar; notification contract before user notices.
- Status: `BLOCKED_DECISION` overall; items 1.1, 1.2, and current four-role behavior in 1.4 are `APPROVED` carry-forward only.

##### C1-CAP-CUSTOMER - customer, phone, classification, export, and 360 profile

- Source wording: section 2, items 2.1-2.5, phone identity note, and safe-deactivation note.
- Approved normalized wording: preserve scoped Customer/CustomerPhone CRUD, search/order/page, Iranian phone normalization, active uniqueness, one active primary phone, and safe Customer deactivation. Customer classification, postal code, document relationship, export, bounded bulk actions, and aggregate profile are included additions awaiting contracts.
- Business owner: `BLOCKED_DECISION`; customer-data owner not named.
- Target users/roles/workstreams: current Sales Agent own/assigned and elevated company scope carry forward; after-sales/minimum lookup and new bulk/export scope unresolved.
- Trigger/input: current manual Customer and phone forms; classification, postal-code vocabulary/validation, document association, bulk selection, and 360 event inputs unresolved.
- Stored data/source of truth: current Customer and CustomerPhone are authoritative for existing fields. No Category, postal-code contract, Invoice link, generic activity stream, or aggregate profile entity is approved.
- Allowed transitions: safe create/edit/deactivate and phone deactivate stay; category lifecycle, merge, bulk action, and document-link transitions unresolved.
- Filters/date/time: current search/order/page stay; category/postcode/document/activity filters and historical/current address semantics unresolved.
- UI/API contract level: current customer list/detail routes and versioned APIs stay. New export/bulk/360 routes are not approved.
- Authorization/object scope: existing backend Customer/phone scoping stays; export, bulk, aggregate activity, after-sales lookup, and document visibility require exact row/field scope.
- Audit: existing deactivation and sensitive writes stay; export, bulk action, classification, merge, and profile-event audit/retention unresolved.
- Migration/data import impact: none for carry-forward; new fields/entities and any legacy postal/category data need additive migration/preflight only after approval.
- Acceptance examples: current normalization/duplicate/primary/direct-ID cases carry forward; need postal examples, category tree/flat choice, empty category, export columns, bulk partial-failure policy, and 360 ordering/redaction examples.
- Dependencies: role matrix; sales-document decision; activity-source registry; file/privacy policy if profile contains documents.
- Status: `BLOCKED_DECISION` overall; core CRUD/search/phone/deactivate behavior is `APPROVED` carry-forward.

##### C1-CAP-LEAD - lead intake, assignment, history, status, and pipeline expansion

- Source wording: section 3, items 3.1-3.5 and notes covering conversion, priority, archive, opportunity, full pipeline, and final statuses.
- Approved normalized wording: preserve Lead create/list/retrieve/permitted edit, source/campaign/product/notes/follow-up fields, manual assignment/reassignment to an active Sales Agent, append-only assignment history, reason, and safe audit. All listed lead expansions are included target work but cannot start without state/entity contracts.
- Business owner: `BLOCKED_DECISION`; sales-process owner not named.
- Target users/roles/workstreams: existing Sales Agent scoped operation and elevated company scope carry forward; requested three-role and future team/pipeline ownership unresolved.
- Trigger/input: current manual lead entry and elevated manual reassignment stay; conversion/priority/archive/opportunity/pipeline inputs unresolved.
- Stored data/source of truth: existing Lead and LeadAssignmentHistory stay authoritative. No approved Opportunity/Pipeline entity or final status enum exists.
- Allowed transitions: manual reassignment service stays. Initial assignment algorithm, Lead status list/transitions, conversion, archive/reopen, opportunity stages, loss/win rules, and concurrency behavior unresolved.
- Filters/date/time: current search/order/page/exact raw status display stay; approved status, priority, stage, owner, campaign, product, and date semantics for future reports unresolved.
- UI/API contract level: current lead list/detail plus assign/history APIs stay; no conversion/archive/opportunity/pipeline route approved.
- Authorization/object scope: existing assigned/own-unassigned rules stay; historical reassignment KPI and future pipeline/team scope unresolved.
- Audit: current assignment/reassignment audit stays; status/conversion/archive/stage audit rules unresolved.
- Migration/data import impact: none for carry-forward; enum/state migration must preflight real values and never rewrite unknown history silently.
- Acceptance examples: current direct-ID/assignee/history/rollback cases carry forward; need exact state-transition table, concurrent transition, archive visibility, conversion cardinality, and historical assignment examples.
- Dependencies: role/team decision; final status and outcome decisions; Customer dedupe; Product scope; reporting denominators.
- Status: `BLOCKED_DECISION` overall; items 3.1-3.5 as currently implemented are `APPROVED` carry-forward.

##### C1-CAP-CONTACT - manual interaction, timeline, follow-up, calendar, and telephony

- Source wording: section 4, items 4.1-4.5 and the missing-duration/recording/telephony/automatic-reminder/repetition/specialist-call-report note.
- Approved normalized wording: preserve append-only manual inbound/outbound Interaction entry for an authorized Lead with phone, bounded outcome, occurrence time, notes, and next follow-up. The customer confirms the specialist call report must be entered manually by the marketer. Timeline/calendar/task/reminder and telephony additions remain target work with undefined contracts.
- Business owner: `BLOCKED_DECISION`; sales/marketing process owner not named.
- Target users/roles/workstreams: authorized Sales Expert/manual marketer and elevated managers; exact relation between marketer and fixed roles unresolved.
- Trigger/input: existing manual Interaction form stays; manual specialist-report fields, meeting/task/calendar/reminder/recurrence, call duration/recording/provider inputs unresolved.
- Stored data/source of truth: Interaction is source for current manual contacts. No approved Activity/Task/Meeting/Reminder/Recording/Telephony entity or unified timeline event registry exists.
- Allowed transitions: Interaction remains append-only. Task/meeting completion, reminder retry, recurrence, correction, recording retention, and provider replay transitions unresolved.
- Filters/date/time: current search/order/page stay; final outcome grouping, qualifying call, marketer report period, timezone/calendar, recurrence, and duration units unresolved.
- UI/API contract level: current interaction list/detail and API stay; no timeline/calendar/telephony/report route approved.
- Authorization/object scope: current Lead-bound Interaction scope stays; timeline cross-entity scope, manager view, recording access, and provider service identity unresolved.
- Audit/security: no raw private payload in audit. Recording consent, encryption, retention, download, provider secrets/signature, and manual report audit unresolved.
- Migration/data import impact: none for carry-forward; future event/report/provider entities require additive migrations and legacy-outcome preflight.
- Acceptance examples: current direction/outcome/direct-ID cases carry forward; need manual marketer report sample, final outcome list, timeline ordering/tie-break, reminder timezone/retry, recurrence, recording consent/retention, and provider failure examples.
- Dependencies: role/workstream decision; final Interaction outcomes; calendar/task contract; communication provider docs; file storage/security policy.
- Status: `BLOCKED_DECISION` overall; 4.1-4.3 current behavior is `APPROVED`; live telephony adapter is also `BLOCKED_EXTERNAL` until official provider/security material exists.

#### Source trace for sections 1 through 4

| Source item | Capability | Reconciled state | Exact reason |
|---|---|---|---|
| 1.1 | C1-CAP-ACC | `APPROVED` | Existing login/logout/me contract and maintained UI carry forward. |
| 1.2 | C1-CAP-ACC | `APPROVED` | Existing scoped user create/search/edit/deactivate carries forward. |
| 1.3 | C1-CAP-ACC | `BLOCKED_DECISION` | Source says four fixed roles and later lists three; existing repository has four security roles. |
| 1.4 | C1-CAP-ACC | `APPROVED` current / `BLOCKED_DECISION` future | Backend scope carries forward; new three-role/team matrix is unresolved. |
| 1.5 | C1-CAP-ACC | `BLOCKED_DECISION` | Session inventory, metadata, own/all revoke, audit, and expiry contract missing. |
| 1.6 | C1-CAP-ACC | `BLOCKED_DECISION` | Avatar storage, notification semantics, export columns and scope missing. |
| 2.1 | C1-CAP-CUSTOMER | `APPROVED` core / `BLOCKED_DECISION` category | Current Customer flow exists; classification model is undefined. |
| 2.2 | C1-CAP-CUSTOMER | `APPROVED` name/phone/address / `BLOCKED_DECISION` postcode/document | Current fields exist; postal and document meaning/source missing. |
| 2.3 | C1-CAP-CUSTOMER | `APPROVED` | Existing scoped search/order/page carries forward. |
| 2.4 | C1-CAP-CUSTOMER | `BLOCKED_DECISION` | Export columns, bulk actions, limits, atomicity, and role scope missing. |
| 2.5 | C1-CAP-CUSTOMER | `BLOCKED_DECISION` | 360 event sources, ordering, retention, redaction, and access missing. |
| phone note | C1-CAP-CUSTOMER | `APPROVED` | Existing label/primary/active/normalization/duplicate controls carry forward. |
| safe deactivate note | C1-CAP-CUSTOMER | `APPROVED` | Hard-delete UI remains replaced by audited deactivation. |
| 3.1-3.5 | C1-CAP-LEAD | `APPROVED` | Current bounded Lead, manual assignment/history/reason/audit contract carries forward. |
| lead expansion note | C1-CAP-LEAD | `BLOCKED_DECISION` | Conversion, priority, archive, Opportunity, Pipeline, statuses, and transitions undefined. |
| 4.1-4.3 | C1-CAP-CONTACT | `APPROVED` | Current authorized append-only manual Interaction contract carries forward. |
| 4.4 | C1-CAP-CONTACT | `BLOCKED_DECISION` | Unified timeline event model and visibility missing. |
| 4.5 | C1-CAP-CONTACT | `BLOCKED_DECISION` | Meeting/task/calendar/reminder/recurrence contract missing. |
| manual specialist call report | C1-CAP-CONTACT | `BLOCKED_DECISION` | Manual marketer entry is confirmed; fields, outcomes, formulas, and acceptance sample missing. |
| duration/recording/telephony | C1-CAP-CONTACT | `BLOCKED_DECISION` plus `BLOCKED_EXTERNAL` | Business, consent, retention, and official provider/security contracts missing. |

- Files changed at this checkpoint: `KARIZ_PROJECT_HANDOFF.md` only.
- Migrations/endpoints/UI routes/authorization behavior: none changed.
- Assumptions: none; mixed source statements are recorded as blockers instead of resolved by guess.
- Exact resume point: sections 1-4 traced; sections 5-7 not yet reconciled.
- Exact next action: reconcile Product, inventory/pricing, Sale/order/invoice/payment, dashboard, reports, XLSX/PDF, and low-priority final-wave markers.

### Checkpoint C1-1.3 - source sections 5 through 7 reconciled

##### C1-CAP-PRODUCT - product catalog and maintained forms

- Source wording: section 5, items 5.1-5.6 and elevated-role management note.
- Approved normalized wording: preserve Product create/list/edit/deactivate, SKU/name/current price/description, Sales Expert active read-only access, elevated-role writes, and search/order/page. Product category and an expanded form are included but require exact fields and lifecycle.
- Business owner: `BLOCKED_DECISION`; catalog owner not named.
- Users/scope: active CRM users read within approved scope; Product write remains elevated only. Exact three-role mapping remains blocked.
- Input/source of truth: current Product is source for current fields. No Category hierarchy or expanded field set is approved.
- Transitions: current create/edit/deactivate stays; category move/deactivate and expanded-field correction unresolved.
- Filters/time: current search/order/page stays; category filters, effective pricing time, and historical catalog visibility unresolved.
- UI/API: current Product routes/API stay; no category or new form endpoint approved.
- Authorization/audit: current elevated writes and safe audit stay; category/bulk changes need scope and audit rules.
- Migration/data impact: none for carry-forward; additive category/field migration only after contract and legacy preflight.
- Acceptance/dependencies: current active/inactive/read-only/direct-ID cases carry forward; need category tree/flat choice, duplicate names, deactivation, expanded field examples, and role mapping.
- Status: `BLOCKED_DECISION` overall; 5.1-5.4 and elevated-only management are `APPROVED`; 5.5-5.6 are blocked.

##### C1-CAP-INVENTORY - warehouse, stock, costing, price variants, discount, and profit

- Source wording: section 5 missing-items note and checked final capability list: warehouse, inventory, purchase price, multiple prices, discount, profit, and inventory report must be added later.
- Approved normalized wording: all named capabilities are confirmed target scope and assigned `FINAL_WAVE_LOW`; no inventory or finance semantics are inferred.
- Business owner/users: `BLOCKED_DECISION`; warehouse/finance owners, operators, approvers, and visibility not named.
- Trigger/input/source of truth: warehouse/product/stock movement/purchase cost/price list/discount inputs and authoritative source unresolved.
- Stored data: no approved Warehouse, StockItem, StockMovement, Cost, PriceList, Discount, or valuation entity.
- Transitions/invariants: receipt, issue, reserve, release, adjustment, transfer, negative-stock policy, unit conversion, lot/serial, costing, price effectiveness, discount stacking, cancellation, and concurrency unresolved.
- Filters/date/formulas: warehouse/product/date/status filters, valuation method, profit formula, tax/discount treatment, returns, and snapshot date unresolved.
- UI/API/auth/audit: no route shape approved; least privilege, dual approval, stock/cost secrecy, audit, and export scope unresolved.
- Migration/import: new schema and possible opening balances/import require reviewed preflight/reconciliation/rollback; no migration approved in C1-1.
- Acceptance/dependencies: need real product/warehouse examples, concurrent stock cases, opening balance, valuation/profit examples, correction/return cases, and reconciliation owner. Depends on Product, Document, Finance, role, and import decisions.
- Status: `BLOCKED_DECISION`; priority `FINAL_WAVE_LOW`.

##### C1-CAP-SALE - existing operational Sale

- Source wording: section 6, items 6.1-6.4 and cancellation/no-hard-delete note, limited to behavior that maps exactly to current Sale.
- Approved normalized wording: preserve confirmed Sale creation for an authorized Lead, active Product, positive quantity, server-owned product/price snapshot and total, search/filter/list/detail, and dedicated audited cancellation by authorized elevated roles. Sale stays operational and is not an accounting Invoice.
- Business owner: current sales owner not named; existing contract carries forward.
- Users/scope: scoped Sales Expert creation/read; elevated company read/cancel under existing four-role contract pending role remap.
- Input/source of truth: Lead, Product, quantity, notes; Sale snapshot and server-derived Customer/seller/status/time are authoritative.
- States: `confirmed` and `cancelled` only for current Sale; unrestricted edit/correction/hard delete remain forbidden.
- Filters/date: current search/order/page/status and `sold_at` semantics stay.
- UI/API/auth/audit: current Sale routes/API and create/cancel service stay; direct-ID masking and server-owned fields stay.
- Migration/data impact: none.
- Acceptance/dependencies: current snapshot arithmetic, scope, cancel conflict, audit, and report exclusion cases carry forward. Depends on exact future role mapping.
- Status: `APPROVED` carry-forward only; this approval does not approve Order, Invoice, Payment, tax, discount, PDF, or postal behavior.

##### C1-CAP-DOCUMENT - order, quotation, invoice, geography, postal workflow, and PDF

- Source wording: section 6 items 6.4-6.6, note that 6.6 through a nonexistent 6.9 are template-only, the full invoice/order rule gap, and checked final items for quotation/accounting invoice and operational PDF.
- Approved normalized wording: Order, quotation, accounting Invoice, related geography/postal reporting, print, and PDF belong to target scope. A minimal internal operational sales document may be scheduled earlier only if separately approved to satisfy Client-1 reports; full accounting/quotation/PDF scope is `FINAL_WAVE_LOW`.
- Business owner: `BLOCKED_DECISION`; sales/accounting/legal/shipping owners not named.
- Users/scope: creators, approvers, correctors, viewers, and sales/after-sales visibility unresolved.
- Trigger/input/source of truth: whether current Sale, new Order, new internal document, or accounting Invoice is source remains unresolved; line items, numbering, Customer/Product snapshots, amounts, tax, discount, creation/import, and fiscal authority unresolved.
- Stored data: no approved Order, OrderItem, Invoice, InvoiceItem, postal current/history, or PDF artifact entity.
- States/transitions: draft/issue/register/cancel/correct/return/postal transitions, immutable issuance, numbering gaps, correction document, and hard-delete policy unresolved.
- Filters/date/formulas: document date, issue date, sale date, current/historical province/city/postal state, null values, count unit, cancellation inclusion, and timezone/calendar unresolved.
- UI/API: source labels are template evidence only; no create/edit/status/print/PDF route shape approved.
- Authorization/audit/security: object scope, financial field custody, postal actor, PDF privacy/download, audit details, and direct-ID behavior need exact matrix.
- Migration/import: new additive schema plus legacy/order/invoice import/reconciliation may be required; no migration or backfill approved.
- Acceptance/dependencies: need redacted document, numbering/tax/discount examples, city/province snapshot examples, exact postal transition table, cancellation/correction, PDF layout/sign-off, and report totals. Depends on role, Product, Sale, Customer geography, Inventory if stock-affecting, Finance if payable, and file policy.
- Status: `BLOCKED_DECISION`; full quotation/accounting/PDF portion priority `FINAL_WAVE_LOW`. Source numbering `6.6-6.9` is ambiguous because item 6.9 is absent.

##### C1-CAP-FINANCE - payment, customer account, receivable, cheque, and installment

- Source wording: section 6 items 6.7-6.8, finance-rule gap, checked payment/cheque/installment/customer-account item, and section 7 receivables requirement.
- Approved normalized wording: named finance capabilities belong to target scope and `FINAL_WAVE_LOW`; no ledger/accounting behavior is approved from template pages.
- Business owner/users: `BLOCKED_DECISION`; finance owner, cashier, approver, manager, and visibility not named.
- Trigger/input/source of truth: payment method, amount/currency, allocation, customer/document relation, external gateway/manual source, cheque/installment schedule, and account balance authority unresolved.
- Stored data: no approved Payment, Allocation, CustomerLedger, Cheque, Installment, Settlement, Refund, or reconciliation entity.
- States/invariants: pending/confirmed/failed/reversed, idempotency, partial/overpayment, allocation, reversal, bounced cheque, installment arrears, balance correction, and immutable ledger rules unresolved.
- Filters/date/formulas: payment/effective/value dates, currency/rounding, receivable aging, outstanding balance, cancellation/refund, and timezone unresolved.
- UI/API/auth/audit/security: no route approved; financial least privilege, dual control, secret/provider boundary, audit, export, and redaction unresolved.
- Migration/import: new schema and opening customer balances/import require signed reconciliation; no migration approved.
- Acceptance/dependencies: need payment/account samples, balance equations, correction/reversal, duplicate/replay, cheque/installment, failed provider, reconciliation, and permission examples. Depends on Document, role, external gateway/accounting contracts, and backup/recovery.
- Status: `BLOCKED_DECISION`; any live gateway/accounting adapter also `BLOCKED_EXTERNAL`; priority `FINAL_WAVE_LOW`.

##### C1-CAP-REPORT - current performance report, dashboard, extended reports, profit/loss, XLSX/PDF, and report builder

- Source wording: section 7 items 7.1-7.7, current filters note, and missing profit/loss, receivables, PDF, and dynamic report-builder note.
- Approved normalized wording: preserve current predefined user-performance JSON/XLSX metrics and filters exactly. Visual dashboard, detailed drill-down, customer/payment/event/statement panels, product/sale/return/order/shipping reports, profit/loss, receivables, operational PDF, and dynamic report builder are included target additions; marked advanced additions are `FINAL_WAVE_LOW`.
- Business owner: `BLOCKED_DECISION`; report owner/sign-off not named.
- Users/scope: current own/company scope carries forward; every new report/drill-down/export needs exact role and row/field scope.
- Trigger/input/source of truth: current Customer.created_by and confirmed Sale.sold_by/sold_at totals stay. New source tables and formulas are unresolved and may not use template numbers.
- Stored data: current report is projection only; dashboard caches/snapshots, saved definitions, dynamic queries, and generated PDF storage are unapproved.
- States: none for current projection; generated-export lifecycle, saved report lifecycle, and refresh/as-of behavior unresolved.
- Filters/date/formulas: current half-open timezone-aware range, permitted user, and Product filter stay. New metrics need exact numerator/denominator, status inclusion, reassignment, return, tax/discount/cost, receivable, geography/postal, timezone/Jalali, grouping, zero/null, and tie-break rules.
- UI/API: current `/reports/user-performance/`, JSON, and XLSX stay. Dashboard/drill-down/extended report/PDF/builder route shapes unapproved.
- Authorization/audit/security: current JSON/XLSX parity and formula-injection defense stay; new exports, saved queries, dynamic field allowlists, query bounds, and audit need contracts.
- Migration/import: none for current report; new domains must exist first; saved/dynamic report entities only after bounded design.
- Acceptance/dependencies: current four metric and zero cases carry forward. Need sample desired report, drill-down rows, chart totals, product/return/order/shipping and P&L/receivable formulas, PDF sample, dynamic builder bounds, query-growth, and export parity examples.
- Status: `BLOCKED_DECISION` overall; 7.1-7.4 are `APPROVED`; ActivityLog part of 7.6 exists but payment/customer-statement/event aggregation does not. Profit/loss, receivables, PDF, and dynamic builder priority `FINAL_WAVE_LOW`.

#### Source trace for sections 5 through 7

| Source item | Capability | Reconciled state | Exact reason/priority |
|---|---|---|---|
| 5.1-5.4 | C1-CAP-PRODUCT | `APPROVED` | Existing Product contract carries forward. |
| 5.5-5.6 | C1-CAP-PRODUCT | `BLOCKED_DECISION` | Category model and expanded fields/forms missing. |
| Product elevated-role note | C1-CAP-PRODUCT | `APPROVED` current / `BLOCKED_DECISION` role remap | Existing elevated-only writes stay; requested three-role mapping unresolved. |
| inventory/pricing/profit missing list | C1-CAP-INVENTORY | `BLOCKED_DECISION` | Target confirmed; all movement, costing, pricing, discount, profit, concurrency, and report rules missing; `FINAL_WAVE_LOW`. |
| 6.1-6.3 | C1-CAP-SALE | `APPROVED` | Maps exactly to current server-snapshotted confirmed Sale. |
| 6.4 | C1-CAP-SALE + C1-CAP-DOCUMENT | `APPROVED` only for Sale search/filter/cancel; `BLOCKED_DECISION` for Invoice | Repository has no Invoice or generic Invoice status edit. |
| 6.5-6.6 | C1-CAP-DOCUMENT | `BLOCKED_DECISION` | Order/Invoice pages are template evidence; model/workflow absent; full scope `FINAL_WAVE_LOW`. |
| 6.7-6.8 | C1-CAP-FINANCE | `BLOCKED_DECISION` | Payment/account pages are template evidence; financial contract absent; `FINAL_WAVE_LOW`. |
| section 6 note | C1-CAP-SALE/DOCUMENT/FINANCE | `APPROVED` safety boundary | Sale cancel stays audited; unrestricted financial edit and hard delete stay forbidden. Missing 6.9 is recorded, not invented. |
| 7.1-7.4 | C1-CAP-REPORT | `APPROVED` | Current exact metrics, filters, and XLSX carry forward. |
| 7.5 | C1-CAP-REPORT | `BLOCKED_DECISION` | Dashboard cards/charts and refresh/metric semantics missing. |
| 7.6 | C1-CAP-REPORT + C1-CAP-FINANCE | `APPROVED` only for current ActivityLog; otherwise `BLOCKED_DECISION` | Payment/event/customer-statement aggregation absent. |
| 7.7 | C1-CAP-REPORT | `BLOCKED_DECISION` | Product/Sale/return/order/shipping formulas and sources missing. |
| profit/loss, receivable, PDF, builder | C1-CAP-REPORT/FINANCE | `BLOCKED_DECISION` | Target confirmed; exact accounting/query/security contract missing; `FINAL_WAVE_LOW`. |

- Files changed at this checkpoint: `KARIZ_PROJECT_HANDOFF.md` only.
- Migrations/endpoints/UI routes/authorization behavior: none changed.
- Assumptions: Sale remains distinct from Order/Invoice/Payment; no legal/accounting or report meaning inferred.
- Exact resume point: sections 1-7 traced; sections 8-10 and original seven provisional requirements remain.
- Exact next action: reconcile calendar/projects/files/communications, search/import, platform/runtime/UI, automation/integrations/PWA/anomaly detection, then map all seven original C1 requirement IDs.

### Checkpoint C1-1.4 - source sections 8 through 10 and original seven IDs reconciled

##### C1-CAP-COLLAB - calendar, tasks, projects, activities, and reminders

- Source wording: 8.1-8.2 plus meeting/calendar/task/reminder material in 4.5 and automatic reminder/recurrence note.
- Approved normalized wording: all named collaboration capabilities belong to target scope; none is operational from template shells.
- Owner/users/input/source: business owner, creator/assignee/watchers, role scope, Customer/Lead/document relation, event/task fields, timezone, recurrence, reminder channel, and source of truth unresolved.
- States/filters/UI/API: task/event/project states and transitions, priority, due/complete/reopen/archive, recurrence exceptions, calendar range, filters, bounds, and routes unresolved.
- Authorization/audit/migration: object sharing, manager scope, private events, assignment audit, reminder payload redaction, new entities, and legacy import unresolved.
- Acceptance/dependencies: need end-to-end task/event examples, timezone/DST/calendar cases, recurrence edits, permission/direct-ID cases, notification failures, desktop/mobile UAT. Depends on role, notification, and activity-timeline contracts.
- Status: `BLOCKED_DECISION`; priority not explicitly lowered by customer.

##### C1-CAP-FILE - operational folder, file, and document management

- Source wording: 8.3 and checked operational file/document item.
- Approved normalized wording: operational file/document management is confirmed target scope and `FINAL_WAVE_LOW`; current template file pages are not capability proof.
- Owner/users/input/source: data owner, uploader/reader/admin scope, entity links, file classes, storage backend/location, size/type/quota, metadata, and source of truth unresolved.
- States/security: upload/version/replace/archive/delete/retention/legal hold, malware quarantine/release, encryption, signed download, path safety, content disposition, and secret scanning unresolved.
- UI/API/audit/migration: no route approved; every upload/download/permission/version action needs bounded audit and direct-ID protection; storage migration/backup/restore contract absent.
- Acceptance/dependencies: need safe file samples, malicious/oversize/type-spoof/path cases, version/retention/recovery, role leaks, browser download, backup/restore. Depends on role, storage, scanner, backup, Document, Customer, and After-sales contracts.
- Status: `BLOCKED_DECISION`; storage/scanner/runtime also `BLOCKED_EXTERNAL`; priority `FINAL_WAVE_LOW`.

##### C1-CAP-COMMS - SMS, external email, and telephony providers

- Source wording: section 8 note and final missing-capability list; includes the initial inbound-SMS reporting dependency.
- Approved normalized wording: communication capabilities belong to target scope. Manual Interaction remains separate. No live provider adapter may be invented without official material.
- Owner/users/input/source: provider owner, sending/receiving users, consent/opt-out, templates, recipient source, sender identity, credentials, webhook/polling, provider IDs, and message body policy unresolved.
- States/security: queue/send/deliver/fail/retry/cancel/replay/idempotency, signature/authentication, rate/cost limits, retention, redaction, and incident behavior unresolved.
- Filters/time/UI/API/audit: message/call date basis, Asia/Tehran and calendar presentation, report filters, routes, scope, body/recording access, and safe audit unresolved.
- Migration/acceptance/dependencies: provider-neutral storage may need new entities; require official docs and sanitized examples, duplicate/replay/signature/rate/time-boundary/consent tests. Depends on phone normalization, role, notification, file/recording policy, and provider access.
- Status: `BLOCKED_DECISION`; live adapters `BLOCKED_EXTERNAL`; priority not globally lowered by customer because inbound SMS is an original Client-1 requirement.

##### C1-CAP-SEARCH - module search, global search, saved filters, and XLSX import

- Source wording: section 9 items 9.1-9.6, current searchable modules, and low-importance missing-items note.
- Approved normalized wording: preserve current scoped module search, strict ordering/page, raw Lead/Sale status filters, report range/user/Product filters, and XLSX export parity. Global multi-module search, saved filters, and bulk XLSX import are target scope in `FINAL_WAVE_LOW`.
- Owner/users/input/source: current model fields remain source. Global indexed fields/ranking/result shape, inactive/history inclusion, saved-filter owner/share/version, and import template/mapping unresolved.
- States/filters: saved filter create/update/share/delete; import upload/preview/validate/apply/fail/retry/idempotency/rollback; limits, dedupe, partial versus atomic behavior unresolved.
- UI/API/auth/audit/security: no new route approved; role/object scope must be applied before results, saved filters, export, or import. Macro/formula/file abuse, row/cell limits, hidden fields, and audit unresolved.
- Migration/acceptance/dependencies: possible SavedFilter/ImportJob schema; need all-role leak, stable rank/order, empty/invalid/repeated query, direct-ID, preview, duplicate/replay, rollback, and large-file cases. Depends on every searchable/imported domain and job/file policy.
- Status: current 9.1-9.5 `APPROVED`; 9.6/global/saved/import `BLOCKED_DECISION`, priority `FINAL_WAVE_LOW`.

##### C1-CAP-PLATFORM - repository API, security, audit, health, and active UI contract

- Source wording: 10.1-10.8, 10.11, current Persian/RTL/brand statement, and abnormal-activity item.
- Approved normalized wording: preserve versioned `/api/v1/`, session/CSRF, read-only safe audit, request IDs, password/throttle/body/depth/error guards, direct-ID isolation, controlled non-production schema/docs, live/ready health, and Persian RTL Kariz shell. Template page presence remains non-operational.
- Owner/users/source: current technical contracts are authoritative. Security/operations owners and abnormal-activity business/security owner not named.
- States/UI/API/auth/audit: current contracts stay. Active pages added later must use real backend scope and loading/empty/error states. Abnormal-activity signals, threshold/model, response, false-positive handling, access, retention, and audit are unresolved.
- Migration/acceptance/dependencies: none for carry-forward; anomaly work may add bounded security events only after contract. Existing repository tests carry forward; target browser/edge proof remains external.
- Status: 10.1-10.8 `APPROVED` repository baseline; 10.11 `BLOCKED_EXTERNAL` for target browser proof; anomaly detection `BLOCKED_DECISION`.

##### C1-CAP-RUNTIME - PostgreSQL, Compose, Nginx, backup, restore, and target operations

- Source wording: 10.9-10.10, backup note, and scheduled real-customer backup item.
- Approved normalized wording: repository configuration/tools are required baseline; real PostgreSQL/Compose/Nginx/TLS/browser/backup/restore/load/scan proof and target schedule/destination/owners are mandatory release gates.
- Owner/source: release, database, security, backup, rollback, and evidence owners; target host, image digests, domain/TLS, backup/off-host destinations, retention, RPO/RTO, schedule, and abort rule unresolved externally.
- States/security: exact deploy/write-stop/backup/restore/rollback procedures in ops runbooks stay; no volume/data deletion or in-place restore.
- Acceptance/dependencies: `EXT-001` through `EXT-007` and `OPS-001` through `OPS-006` remain. Need native PostgreSQL, exact images, edge, TLS, browser, backup checksum/no-network restore, load, scans, owners, and UAT.
- Status: repository artifacts `APPROVED`; execution `BLOCKED_EXTERNAL`. Priority `RELEASE_GATE`, not a deferrable nice-to-have even though it occurs after feature waves.

##### C1-CAP-LATE - workflow automation, dynamic permissions, external commerce/accounting links, PWA, and anomaly expansion

- Source wording: final missing-capability list and checked website/store/gateway/accounting integration item.
- Approved normalized wording: every named family is included in the end target. External website/store/gateway/accounting links are `FINAL_WAVE_LOW`. Priority for automation, dynamic permission design, PWA, and anomaly detection was not explicitly lowered.
- Owner/users/input/source: owners, triggers, action catalogs, integration directions, credentials, reconciliation authority, offline data, and detection signals unresolved.
- States/security: automation version/publish/run/retry/idempotency, dynamic grant/revoke/escalation, integration replay/reconcile, offline conflict/sync, anomaly review/respond/close all unresolved.
- UI/API/auth/audit/migration: no entity or route approved. Dynamic permission work directly conflicts with the source's fixed-role wording and current fail-closed role contract; do not implement until the customer chooses one model.
- Acceptance/dependencies: need bounded automation/integration/PWA/security contracts, official provider docs, replay/conflict/offline/escalation/incident tests. Depends on stable domain models, role decision, external providers, job/outbox policy, and runtime proof.
- Status: `BLOCKED_DECISION`; external adapters `BLOCKED_EXTERNAL`; checked commerce/accounting integrations priority `FINAL_WAVE_LOW`.

#### Source trace for sections 8 through 10 and final missing list

| Source item | Capability | Reconciled state | Exact reason/priority |
|---|---|---|---|
| 8.1-8.2 | C1-CAP-COLLAB | `BLOCKED_DECISION` | Only template shell; workflow/state/scope missing. |
| 8.3 | C1-CAP-FILE | `BLOCKED_DECISION` plus `BLOCKED_EXTERNAL` | Operational storage/security/scanner absent; `FINAL_WAVE_LOW`. |
| SMS/email/telephony note | C1-CAP-COMMS | `BLOCKED_DECISION` plus `BLOCKED_EXTERNAL` | Provider/security/consent/idempotency contracts absent. |
| 9.1-9.5 | C1-CAP-SEARCH | `APPROVED` | Existing scoped module behavior carries forward. |
| 9.6 and missing search/import list | C1-CAP-SEARCH | `BLOCKED_DECISION` | Global/saved/import contracts absent; customer says low importance; `FINAL_WAVE_LOW`. |
| 10.1-10.8 | C1-CAP-PLATFORM | `APPROVED` | Existing repository contracts carry forward. |
| 10.9 | C1-CAP-RUNTIME | `APPROVED` config / `BLOCKED_EXTERNAL` runtime | Repository config is not live proof. |
| 10.10 | C1-CAP-RUNTIME | `APPROVED` guarded tools / `BLOCKED_EXTERNAL` real backup | Schedule/destination/owner/restore proof missing; `RELEASE_GATE`. |
| 10.11/home note | C1-CAP-PLATFORM | `APPROVED` maintained shell / `BLOCKED_EXTERNAL` target proof | Template pages need real backend, cleanup, and browser proof. |
| Opportunity/full pipeline | C1-CAP-LEAD | `BLOCKED_DECISION` | Target included; entity/state/conversion rules absent. |
| Inventory | C1-CAP-INVENTORY | `BLOCKED_DECISION` | Target included; `FINAL_WAVE_LOW`. |
| Quotation/accounting invoice | C1-CAP-DOCUMENT | `BLOCKED_DECISION` | Target included; `FINAL_WAVE_LOW`. |
| Payment/cheque/installment/account | C1-CAP-FINANCE | `BLOCKED_DECISION` | Target included; `FINAL_WAVE_LOW`. |
| Notification/automation | C1-CAP-COLLAB/C1-CAP-LATE | `BLOCKED_DECISION` | Target included; trigger/delivery/workflow contract absent. |
| SMS/email/telephony | C1-CAP-COMMS | `BLOCKED_DECISION` plus `BLOCKED_EXTERNAL` | Target included; provider documents absent. |
| Operational files/documents | C1-CAP-FILE | `BLOCKED_DECISION` plus `BLOCKED_EXTERNAL` | Target included; `FINAL_WAVE_LOW`. |
| Dynamic roles/permissions | C1-CAP-LATE | `BLOCKED_DECISION` | Conflicts with fixed-role statements; no implementation allowed. |
| Website/store/gateway/accounting links | C1-CAP-LATE | `BLOCKED_DECISION` plus `BLOCKED_EXTERNAL` | Direction/provider/reconciliation absent; `FINAL_WAVE_LOW`. |
| Bulk XLSX import | C1-CAP-SEARCH | `BLOCKED_DECISION` | Target included; `FINAL_WAVE_LOW`. |
| Operational PDF | C1-CAP-DOCUMENT/C1-CAP-REPORT | `BLOCKED_DECISION` | Target included; `FINAL_WAVE_LOW`. |
| Installable web app | C1-CAP-LATE | `BLOCKED_DECISION` | Offline/cache/sync/update/security contract absent. |
| Abnormal activity detection | C1-CAP-PLATFORM/C1-CAP-LATE | `BLOCKED_DECISION` | Signals/thresholds/response/owner absent. |
| Real scheduled backup | C1-CAP-RUNTIME | `BLOCKED_EXTERNAL` | Target host/schedule/destination/owner/RPO/RTO absent; mandatory `RELEASE_GATE`. |

#### Reconciliation of the seven initial Client-1 requirements

##### C1-REQ-001 - sales panel without an application seat cap

- Final-source comparison: sales/account/customer/lead/interaction/product/Sale/report capabilities are reaffirmed; no-seat-cap wording and concurrent capacity are not restated.
- Normalized contract: current maintained sales shell is carry-forward; do not add an application seat limit. Explicit customer confirmation of licensing meaning and load target still required before acceptance wording.
- Owner/users: owner not named; Sales Expert/Manager named, System Manager mapping blocked.
- Trigger/data/workflow: existing domain contracts only; new role/workstream behavior unresolved.
- Filters/time/UI/API: existing routes and filters carry forward; panel completeness and acceptance page list unresolved.
- Authorization/audit/migration: current scope stays; three-to-four role mapping and account migration unresolved.
- Acceptance/dependencies: need explicit no-seat-cap confirmation, peak concurrency/abort rule, role matrix, page/action matrix, inactive/account lifecycle UAT. Depends first on C1-CAP-ACC.
- Status: `BLOCKED_DECISION`; not an implementation contract yet.

##### C1-REQ-002 - after-sales panel without an application seat cap

- Final-source comparison: final list has support/file/communication families but does not define an after-sales case panel or repeat no-seat-cap wording.
- Normalized contract: after-sales remains included from initial intake, but no entity/workflow is approved.
- Owner/users: owner, after-sales operator identity/workstream, manager boundary, and cross-panel access unresolved.
- Trigger/data/states: creator, assignee, Customer/Sale/Document link, fields, statuses, transitions, reassign, close/reopen, SLA, retention unresolved.
- Filters/time/UI/API/auth/audit: all routes, filters, date basis, scope, audit, direct-ID, export, and errors unresolved.
- Migration/acceptance/dependencies: new schema likely; need opening-to-close sample, role matrix, assignment/status table, object-scope UAT. Depends on identity and approved Document relation.
- Status: `BLOCKED_DECISION`; not an implementation contract yet.

##### C1-REQ-003 - detailed management performance and drill-down

- Final-source comparison: 7.1-7.4 confirm current performance baseline; final source does not define extra metrics or drill-down rows.
- Normalized contract: current four metrics/filters/XLSX remain approved; detailed extension remains blocked.
- Owner/users: report owner and exact management roles unresolved.
- Trigger/data/formulas: Customer/Sale current formulas stay; new numerator/denominator, cancellation/reassignment, interaction/outcome and drill-down record types unresolved.
- Filters/time/UI/API/auth/audit: timezone/calendar, half-open ranges for new sources, filters, row limits, drill-down routes, JSON/XLSX/UI parity, scope, and export audit unresolved.
- Migration/acceptance/dependencies: projection preferred; any snapshot entity needs approval. Need redacted desired report and exact expected totals. Depends on role, Lead status/outcome, Document/Finance domains as used.
- Status: `BLOCKED_DECISION`; current baseline is `APPROVED` only.

##### C1-REQ-004 - inbound SMS count by day and hour

- Final-source comparison: communications are required but explicitly lack backend/provider contract; day/hour report wording is not detailed.
- Normalized contract: provider-neutral secure inbound storage/report may proceed only after fields/count/time/scope approval; live adapter needs official docs.
- Owner/users: provider/business owner and report roles unresolved.
- Trigger/data/states: webhook versus polling, authentication/signature, replay/idempotency key, sender/recipient, retained metadata/body, received timestamp, duplicate lifecycle unresolved.
- Filters/time/UI/API/auth/audit: timezone/day-hour boundary, Jalali/Gregorian display, provider/recipient filters, bounds, route, scope, logs/audit redaction unresolved.
- Migration/acceptance/dependencies: new entity likely; need sanitized provider samples, duplicate/replay/signature/time-boundary/role/report cases. Depends on C1-CAP-COMMS, phone normalization, role decision.
- Status: core/report `BLOCKED_DECISION`; live adapter `BLOCKED_EXTERNAL`.

##### C1-REQ-005 - document count by city and province

- Final-source comparison: Customer geography, Order/Invoice, and extended reports are target scope; counted document and formula remain undefined.
- Normalized contract: no choice between Sale, internal Document, Order, or accounting Invoice is made.
- Owner/users: business/accounting/report owner and viewers unresolved.
- Trigger/data/states: document source, line items, numbering, snapshots, cancel/correct, counted status and authoritative province/city unresolved.
- Filters/time/UI/API/auth/audit: report date, current versus historical geography, null/unknown, filters, drill-down/export, scope, audit unresolved.
- Migration/acceptance/dependencies: likely Document/geography snapshot schema; need redacted sample and expected group totals. Depends on C1-CAP-DOCUMENT, Customer, role.
- Status: `BLOCKED_DECISION`.

##### C1-REQ-006 - incoming-number count by contact status

- Final-source comparison: CustomerPhone/Lead/Interaction/search are reaffirmed; incoming-number and contact-status meanings are absent.
- Normalized contract: no counted unit or status derivation is selected.
- Owner/users: report/process owner and viewers unresolved.
- Trigger/data/states: Lead versus phone/call/SMS/import row, source, dedupe key/window, exact statuses, stored versus derived, no-contact, latest/tie-break unresolved.
- Filters/time/UI/API/auth/audit: date basis, campaign/product/user filters, drill-down/export, row scope, historical/current status, audit unresolved.
- Migration/acceptance/dependencies: may require bounded enum/preflight or projection; need sample rows and totals. Depends on CustomerPhone, Lead, Interaction outcomes, role.
- Status: `BLOCKED_DECISION`.

##### C1-REQ-007 - registered document count by postal status

- Final-source comparison: Order/Invoice/shipping reports are target scope; registered and postal workflow meanings are absent.
- Normalized contract: no postal enum/history/provider or report formula is selected.
- Owner/users: document/shipping/report owner and actors unresolved.
- Trigger/data/states: registered meaning, document source, exact postal states/transitions/history, actor, manual/provider source, tracking, return/failure/cancel unresolved.
- Filters/time/UI/API/auth/audit: current versus historical status, report date, filters, drill-down/export, scope, audit unresolved.
- Migration/acceptance/dependencies: likely Document/postal history schema; need status table, redacted examples, expected totals, provider docs if live. Depends on C1-REQ-005/C1-CAP-DOCUMENT first.
- Status: `BLOCKED_DECISION`.

- Files changed at this checkpoint: `KARIZ_PROJECT_HANDOFF.md` only.
- Migrations/endpoints/UI routes/authorization behavior: none changed.
- Exact C1-1 gate result so far: every source family is traced; none is silently dropped or inferred. Carry-forward items are approved, every undefined item is blocked, and all explicitly low-priority additions are retained in `FINAL_WAVE_LOW`.
- Exact resume point: source trace complete; consolidated decision register, acceptance matrix, and dependency order remain.
- Exact next action: create one consolidated unresolved-decision register and implementation order, then update `BACKEND_SPEC.md` only with confirmed target-scope/prioritization facts.

### Checkpoint C1-1.5 - decision register, acceptance matrix, and dependency order

#### Consolidated decision register

| Decision ID | Required decision/source | Current state | Blocks |
|---|---|---|---|
| C1-DEC-GOV-001 | Name business owner, security owner, UAT owner, and final sign-off authority. | `BLOCKED_DECISION` | Approval of every new capability and final acceptance. |
| C1-DEC-SEAT-001 | Confirm no application seat cap, licensed-account meaning, expected total users, peak concurrency, load target, and abort rule. | `BLOCKED_DECISION` | C1-REQ-001/002 acceptance and capacity proof. |
| C1-DEC-ROLE-001 | Four fixed codes; Persian display mapping; Platform Admin custody; Company IT ceiling. | `RESOLVED 2026-08-11` | Codes stay stable. `platform_admin` keeps highest custody; `company_it` cannot grant, target, or manage it. Team/workstream scope stays in C1-DEC-TEAM-001/AFTER-001. |
| C1-DEC-TEAM-001 | Define Sales Manager team boundary, team membership/lifecycle, and company-wide exceptions. | `BLOCKED_DECISION` | Manager user admin, assignment, reporting, pipeline, and bulk operations. |
| C1-DEC-AFTER-001 | Define after-sales identity/workstream, case fields, Customer/Document link, assignee, states/transitions, manager scope, close/reopen, retention, and sample. | `BLOCKED_DECISION` | C1-REQ-002 and C1-5. |
| C1-DEC-LEAD-001 | Final Lead statuses/transitions, initial assignment, conversion target, priority, archive, Opportunity/Pipeline model, reassignment KPI policy. | `BLOCKED_DECISION` | Lead expansion, contact status, pipeline, performance. |
| C1-DEC-CONTACT-001 | Final Interaction outcomes, qualifying call, manual marketer report fields/formulas, timeline events, no-contact/latest tie-break. | `BLOCKED_DECISION` | C1-REQ-006, specialist call report, detailed performance. |
| C1-DEC-CALENDAR-001 | Event/task/project fields, owner/assignee, states, recurrence, timezone, reminders, notification channels, visibility. | `BLOCKED_DECISION` | Collaboration/timeline/automatic reminder. |
| C1-DEC-DOC-001 | Distinguish Sale, Order, internal sales document, quotation, and accounting Invoice; define cardinality, line items, numbering, amounts, rounding, tax, discount, issue/cancel/correct, import/source, hard-delete rule. | `BLOCKED_DECISION` | C1-3, C1-REQ-005/007, Finance, Inventory, PDF. |
| C1-DEC-GEO-001 | Province/city vocabulary, postal-code format, one/many addresses, required/null behavior, validity, current versus immutable document snapshot, report date. | `BLOCKED_DECISION` | Customer expansion and C1-REQ-005. |
| C1-DEC-POST-001 | Exact postal states/transitions/history, registered meaning, actor, manual/provider source, tracking, return/failure/cancel, current versus historical grouping. | `BLOCKED_DECISION` | C1-REQ-007 and shipping reports. |
| C1-DEC-INCOMING-001 | Define incoming-number counted unit/source, dedupe key/window, date basis, and link to phone/Lead/call/SMS/import. | `BLOCKED_DECISION` | C1-REQ-006. |
| C1-DEC-PERF-001 | Exact detailed metrics/denominators, reassignment/cancel/return treatment, drill-down rows, filters, timezone/calendar, columns, bounds, visibility, sample totals. | `BLOCKED_DECISION` | C1-REQ-003, dashboard, extended reports. |
| C1-DEC-SMS-001 | Provider, official docs, webhook/polling, signature/auth, replay/idempotency, retained fields/body, received time, timezone/calendar, filters, roles, sanitized samples. | `BLOCKED_DECISION` plus `BLOCKED_EXTERNAL` | C1-REQ-004 and live SMS adapter. |
| C1-DEC-PRODUCT-001 | Category taxonomy/lifecycle and exact expanded Product fields/form rules. | `BLOCKED_DECISION` | Product category/full form. |
| C1-DEC-INVENTORY-001 | Warehouse/stock movement/reservation/concurrency, units/variants, costing, multi-price, discount, profit, returns, reporting, opening balances. | `BLOCKED_DECISION` | C1-CAP-INVENTORY; final wave. |
| C1-DEC-FINANCE-001 | Payment/ledger/allocation/currency/reversal, receivable, cheque/installment, opening balance, reconciliation, roles, samples. | `BLOCKED_DECISION` | C1-CAP-FINANCE and P&L; final wave. |
| C1-DEC-REPORT-001 | Domain-report formulas, dashboard refresh, P&L/receivable basis, PDF layouts/storage, dynamic-builder allowlist/limits/sharing. | `BLOCKED_DECISION` | Extended report/UI/export scope; advanced parts final wave. |
| C1-DEC-FILE-001 | Storage/scanner, type/size/quota, version, link targets, retention/hold/delete, encryption/download, backup/restore, access. | `BLOCKED_DECISION` plus `BLOCKED_EXTERNAL` | Avatar, recording, operational file/document, stored PDF; final-wave file module. |
| C1-DEC-SEARCH-001 | Global fields/rank/result shape, saved-filter ownership/share, XLSX import template/mapping/limits/dedupe/idempotency/atomicity/rollback. | `BLOCKED_DECISION` | Search/import final wave. |
| C1-DEC-INTEGRATION-001 | Per website/store/gateway/accounting/email/telephony adapter: direction/source of truth, mapping, official docs, auth, replay, retry, reconcile, secrets/network/owner. | `BLOCKED_DECISION` plus `BLOCKED_EXTERNAL` | External adapters; checked commerce adapters final wave. |
| C1-DEC-LATE-001 | Automation triggers/actions/version/retry, dynamic permission versus fixed roles, PWA offline/sync/update, anomaly signals/threshold/response. | `BLOCKED_DECISION` | Late expansion families. |
| C1-DEC-RUNTIME-001 | Target OS/resources, images, host/domain/TLS, backup/off-host destination/schedule/retention/RPO/RTO, load abort rule, owners/window. | `BLOCKED_EXTERNAL` | C1-8/C1-9 and production claim. |
| C1-DEC-DELIVERY-001 | One all-capability release versus approved staged delivery; exact normal-priority order among unmarked additions. Low-marked items must remain last either way. | `BLOCKED_DECISION` | Final phase boundaries and acceptance/sign-off plan. |

#### Client-1 capability and acceptance matrix

No row below is `VERIFIED_END_TO_END`. `APPROVED` means the named current contract may carry forward, not target-site proof.

| Capability | Contract | Backend/UI now | Automated proof now | Runtime/UAT | Priority | Main blocker |
|---|---|---|---|---|---|---|
| C1-CAP-ACC | mixed; overall `BLOCKED_DECISION` | current auth/user real; sessions/avatar/notices/export absent | current suite exists | external pending | core | C1-DEC-SEAT/TEAM plus later session/avatar/notices/export contracts |
| C1-CAP-CUSTOMER | mixed; overall `BLOCKED_DECISION` | core/phone real; category/postcode/export/bulk/360 absent | current suite exists | external pending | core + later additions | category/geography/document/scope |
| C1-CAP-LEAD | mixed; overall `BLOCKED_DECISION` | core assignment/history real; status/pipeline expansion absent | current suite exists | external pending | core + later additions | C1-DEC-LEAD-001 |
| C1-CAP-CONTACT | mixed; overall `BLOCKED_DECISION` | manual Interaction real; timeline/calendar/report/telephony absent | current suite exists | provider/target pending | core + later additions | C1-DEC-CONTACT/CALENDAR/INTEGRATION |
| C1-CAP-PRODUCT | mixed; overall `BLOCKED_DECISION` | core real; category/full form gap | current suite exists | external pending | core + later addition | C1-DEC-PRODUCT-001/ROLE |
| C1-CAP-INVENTORY | `BLOCKED_DECISION` | absent | none | not run | `FINAL_WAVE_LOW` | C1-DEC-INVENTORY-001 |
| C1-CAP-SALE | `APPROVED` carry-forward | real | current suite exists | external pending | core | final role/runtime proof |
| C1-CAP-DOCUMENT | `BLOCKED_DECISION` | absent; template shells only | none | not run | minimal report dependency early; full scope `FINAL_WAVE_LOW` | C1-DEC-DOC/GEO/POST |
| C1-CAP-FINANCE | `BLOCKED_DECISION` | absent; template shells only | none | not run | `FINAL_WAVE_LOW` | C1-DEC-FINANCE/DOC |
| C1-CAP-REPORT | mixed; overall `BLOCKED_DECISION` | four metrics/XLSX real; detailed/domain/advanced absent | current suite exists | external pending | core + advanced `FINAL_WAVE_LOW` | C1-DEC-PERF/REPORT/domains |
| C1-CAP-COLLAB | `BLOCKED_DECISION` | template shells only | none | not run | order TBD | C1-DEC-CALENDAR-001 |
| C1-CAP-FILE | `BLOCKED_DECISION`/`BLOCKED_EXTERNAL` | absent; template shells only | none | storage not available | `FINAL_WAVE_LOW` | C1-DEC-FILE-001 |
| C1-CAP-COMMS | `BLOCKED_DECISION`/`BLOCKED_EXTERNAL` | absent; manual Interaction is separate | none | providers absent | SMS core priority; other order TBD | C1-DEC-SMS/INTEGRATION |
| C1-CAP-SEARCH | mixed | module search real; global/saved/import absent | current suite exists | external pending | expansion `FINAL_WAVE_LOW` | C1-DEC-SEARCH-001 |
| C1-CAP-PLATFORM | repository baseline `APPROVED`; additions blocked | API/security/audit/health/shell real | current suite exists | target proof pending | mandatory | C1-DEC-ROLE/LATE/RUNTIME |
| C1-CAP-RUNTIME | config/tools `APPROVED`; execution `BLOCKED_EXTERNAL` | artifacts exist | parser/repo proof only | not proved live | `RELEASE_GATE` | C1-DEC-RUNTIME-001 |
| C1-CAP-LATE | `BLOCKED_DECISION`/`BLOCKED_EXTERNAL` | absent/template only | none | not run | checked integrations `FINAL_WAVE_LOW`; rest TBD | C1-DEC-LATE/INTEGRATION |
| C1-REQ-001 | `BLOCKED_DECISION` | partial sales shell exists | partial current proof | capacity/UAT absent | original Client-1 core | role/seat/capacity |
| C1-REQ-002 | `BLOCKED_DECISION` | absent | none | absent | original Client-1 core | after-sales contract |
| C1-REQ-003 | `BLOCKED_DECISION` | baseline report exists; drill-down absent | baseline proof only | UAT absent | original Client-1 core | metric/drill-down contract |
| C1-REQ-004 | `BLOCKED_DECISION`/`BLOCKED_EXTERNAL` | absent | none | provider absent | original Client-1 core | SMS contract/docs |
| C1-REQ-005 | `BLOCKED_DECISION` | absent | none | absent | original Client-1 core | document/geography contract |
| C1-REQ-006 | `BLOCKED_DECISION` | absent | none | absent | original Client-1 core | unit/contact-status contract |
| C1-REQ-007 | `BLOCKED_DECISION` | absent | none | absent | original Client-1 core | document/postal contract |

#### Approved implementation dependency order

This order reflects technical dependencies plus the customer's instruction to retain marked low-priority work at the end. It does not approve blocked semantics.

1. Resolve C1-DEC-GOV/SEAT/TEAM/AFTER and approve the remaining identity/workstream matrix; C1-DEC-ROLE-001 is resolved; only then run C1-2.
2. Resolve C1-DEC-DOC/GEO/POST and implement the minimum approved operational document/geography/postal foundation required by original reports; only then run C1-3.
3. Resolve C1-DEC-INCOMING/CONTACT/PERF and implement contact-status plus detailed performance/drill-down; only then run C1-4.
4. Resolve C1-DEC-AFTER and the approved Customer/Document relation; only then run C1-5.
5. Resolve C1-DEC-SMS and obtain official provider material; then run C1-6, keeping a live adapter externally blocked when docs remain absent.
6. Implement approved normal-priority additions whose order was not marked low: Product category/form, Lead workflow/pipeline, timeline/calendar/task/activity, notifications/automation, domain reports, PWA/anomaly work only after their individual contracts. C1-DEC-DELIVERY-001 must order these slices.
7. Implement `FINAL_WAVE_LOW`: Inventory/cost/multi-price/discount/profit; full quotation/accounting Invoice; Payment/cheque/installment/customer account; P&L/receivables/PDF/dynamic report builder; operational file/document; global search/saved filters/XLSX import; checked website/store/gateway/accounting integrations.
8. Run one unified C1-7 UI/dashboard/navigation hardening pass over every capability included in the chosen release; no shell-only item may be called operational.
9. Run C1-8 against the exact complete chosen release. Real scheduled backup remains a mandatory release gate, not optional low-priority scope.
10. Run C1-9 target deployment/UAT/cutover and sign-off. If staged delivery is approved, repeat runtime/UAT proof for each exact release slice; do not treat a later target item as delivered early.

- C1-2 start gate: `BLOCKED_DECISION` until C1-DEC-GOV-001, C1-DEC-SEAT-001, C1-DEC-TEAM-001, and C1-DEC-AFTER-001 are approved. C1-DEC-ROLE-001 is resolved.
- Files changed at this checkpoint: `KARIZ_PROJECT_HANDOFF.md` only.
- Migrations/endpoints/UI routes/authorization behavior: none changed.
- Exact resume point: decision register/matrix/order complete; `BACKEND_SPEC.md` still states several now-included families as default-out/blocked without the new Client-1 scope distinction.
- Exact next action: add a narrow confirmed Client-1 scope/prioritization section to `BACKEND_SPEC.md`; keep every detailed unresolved rule blocked and do not change current role behavior.

### Checkpoint C1-1.6 - authoritative specification scope truth updated — HISTORICAL

This checkpoint predates the 2026-08-11 foundation correction. Its role-ambiguity and Git-status statements are superseded by `CURRENT SNAPSHOT`.

- Status: C1-1 reconciliation documentation complete; verification pending.
- Files inspected: bounded complete diff of `BACKEND_SPEC.md` after the edit.
- Files changed:
  - `BACKEND_SPEC.md`: confirmed that every named final-source family belongs to the Client-1 target; recorded `FINAL_WAVE_LOW`; kept all undefined semantics blocked; recorded three-versus-four role contradiction; expanded unresolved-decision list.
  - `KARIZ_PROJECT_HANDOFF.md`: live C1-1 trace, contracts, decisions, matrix, order, and evidence.
- Files deliberately not changed: `docs/backend/API_CONTRACT.md`, `docs/backend/ENTITY_CATALOG.md`, `docs/backend/RELATIONSHIPS.md`, `docs/backend/ERD.mmd`, and `docs/ops/UAT.md`; no new entity, relationship, API, role behavior, or UAT fixture is approved yet.
- Migrations: none created or changed.
- API endpoints changed: none.
- UI routes changed: none.
- Authorization impact: none; existing four role codes remain authoritative until C1-DEC-ROLE-001 is approved.
- Exact commands/results:
  - `git diff -- BACKEND_SPEC.md` -> PASS, exit 0; review shows scope/status text only and no current business-rule promotion.
  - `git status --short` -> PASS, exit 0; ` M BACKEND_SPEC.md` and ` M KARIZ_PROJECT_HANDOFF.md` only.
- Confirmed scope effect: former default-out target families named by the final customer list are no longer dropped; implementation remains blocked until exact contracts exist.
- Assumptions: none; priority lowered only for items explicitly marked later/low/checkmarked by the customer. Unmarked additions keep priority TBD.
- Blockers: decision register C1-DEC-GOV-001 through C1-DEC-DELIVERY-001; provider/runtime items also have external blockers.
- Current Git commit: `bc0233fe815f93aa51a775b381c3885402d2c6bf`.
- Current git status: ` M BACKEND_SPEC.md`; ` M KARIZ_PROJECT_HANDOFF.md`.
- Exact resume point: C1-1 documentation edits complete; run documentation and baseline gates from the C1-1 phase.
- Exact next action: run `git diff --check`, then Django check, migration drift, UTF-8 OpenAPI validation, full suite, and branding scan; record exact results and self-correct until score 9 or higher.

### Checkpoint C1-1.7 - verification in progress — HISTORICAL

This checkpoint predates the 2026-08-11 foundation correction. Its counts and Git status are historical evidence only.

- Active phase: `C1-1`; verification only.
- Files changed: `BACKEND_SPEC.md` and `KARIZ_PROJECT_HANDOFF.md` only.
- Migrations/API endpoints/UI routes/authorization behavior: none changed.
- Exact verification evidence:
  - `git diff --check` -> PASS, exit 0; no whitespace error; only non-failing LF-to-CRLF working-copy notices for the two changed Markdown files.
  - `python manage.py check --settings=config.test_settings` -> PASS, exit 0; `System check identified no issues (0 silenced)`.
- Current Git commit: `bc0233fe815f93aa51a775b381c3885402d2c6bf`.
- Current git status: ` M BACKEND_SPEC.md`; ` M KARIZ_PROJECT_HANDOFF.md`.
- Self-correction score 1: `8/10`.
- [KARIZ_PROJECT_HANDOFF.md sections 1/4/6]: Old live summary still says scoped V1 target and out-of-target modules. Next run can use wrong scope.
- [KARIZ_PROJECT_HANDOFF.md section 18]: Old V4 next action still looks current. Resume can start wrong task.
- Exact resume point: all requested C1-1 gates passed; live-summary consistency fix pending.
- Exact next action: mark old V1 summary as current-core baseline, promote Client-1 expanded target truth at the top, mark old V4 next action superseded, then rerun diff/coverage checks and score again.

### Checkpoint C1-1.8 - final C1-1 handoff — HISTORICAL

This checkpoint predates the 2026-08-11 foundation correction. The old `24`-open-decision count and role contradiction are superseded by `CURRENT SNAPSHOT` and the updated decision register.

- C1-1 status: `BLOCKED_DECISION`; reconciliation is complete, but implementation contracts are not fully approved.
- Active phase: `C1-1` complete; no C1-2 work started.
- Final-source result: every numbered section, note, missing-capability line, and original C1-REQ-001 through C1-REQ-007 is retained and mapped. Nothing is silently removed. Customer-marked later/low additions are required in `FINAL_WAVE_LOW`.
- Approved capability baseline: current auth/profile/user administration; current backend object scoping; Customer/CustomerPhone core; Lead core/manual assignment/history; manual Interaction core; Product core; operational Sale; four exact performance metrics/XLSX; current module search/filter/page; versioned API/security/audit/health/Persian RTL shell; repository runtime configuration/tools. These are carry-forward contracts, not `VERIFIED_END_TO_END` target proof.
- Blocked capability result: every new role/workstream rule, session/avatar/notification/export addition, category/postcode/360, Lead pipeline/state expansion, timeline/calendar/task/call-report/provider work, Inventory, Order/Invoice/postal, Finance, detailed/domain/advanced reports, files, communications, global search/import, automation/dynamic permissions/integrations/PWA/anomaly, and runtime/UAT execution remains blocked by the exact register.
- Original seven result: C1-REQ-001, 002, 003, 005, 006, and 007 are `BLOCKED_DECISION`; C1-REQ-004 is `BLOCKED_DECISION` and its live adapter is `BLOCKED_EXTERNAL`.
- Open decisions: 24 IDs, C1-DEC-GOV-001 through C1-DEC-DELIVERY-001 as enumerated in C1-1.5.
- Highest-priority blockers:
  - [C1-DEC-ROLE-001]: Source says four fixed roles, then names three. Trust and access map unknown.
  - [C1-DEC-SEAT-001]: No-seat-cap and real peak capacity rule not final. Acceptance load unknown.
  - [C1-DEC-TEAM-001]: Sales Manager team bound not set. User and Lead scope unknown.
  - [C1-DEC-AFTER-001]: After-sales workstream and case flow not set. C1-REQ-002 and C1-2/C1-5 access split blocked.
  - [C1-DEC-DOC-001]: Sale, order, internal document, quotation, and accounting invoice meaning not set. C1-3 and reports blocked.
  - [C1-DEC-CONTACT-001]: Contact status and marketer report rule not set. C1-4 blocked.
  - [C1-DEC-SMS-001]: Provider and secure receipt/report rule not set. C1-6 blocked.
- Files inspected: `AGENTS.md`, `BACKEND_SPEC.md`, `KARIZ_PROJECT_HANDOFF.md`, final customer source in the current request, `docs/backend/API_CONTRACT.md`, `docs/backend/ENTITY_CATALOG.md`, `docs/backend/RELATIONSHIPS.md`, `docs/backend/ERD.mmd`, `docs/ops/UAT.md`, bounded diffs, and current Git summaries.
- Files changed:
  - `BACKEND_SPEC.md`: confirmed expanded Client-1 target inclusion and final-low priority without inventing implementation rules; current four-role behavior retained pending decision.
  - `KARIZ_PROJECT_HANDOFF.md`: sole live source now holds complete trace, contract cards, decision register, capability matrix, dependency order, evidence, blockers, and resume point.
- Files not changed: all source code, models, migrations, serializers, services, selectors, views, URLs, templates, static files, tests, backend technical contracts, entity/relationship/ERD docs, and operations runbooks.
- Migrations: none created or changed; drift PASS.
- API endpoints changed: none.
- UI routes changed: none.
- Authorization behavior changed: none.
- Exact verification evidence:
  - read-only probe `rg -l -g '*.py' -g '!**/migrations/**' -g '!**/__pycache__/**' "class Product|class Sale|UserPerformance|user_performance|sales_product_id|average_sale_amount|cancel_sale|create_sale" backend config` -> FAILED, exit 1; safe cause: missing `backend/` path (`os error 2`); repository unchanged.
  - exact resume probe `rg -l -g '*.py' -g '!**/migrations/**' -g '!**/__pycache__/**' "class Product|class Sale|UserPerformance|user_performance|sales_product_id|average_sale_amount|cancel_sale|create_sale" sales reports accounts common config` -> PASS, exit 0; bounded relevant files found.
  - `git diff --check` -> PASS before and after self-correction; only non-failing LF-to-CRLF notices.
  - `python manage.py check --settings=config.test_settings` -> PASS, 0 issues.
  - `python manage.py makemigrations --check --dry-run --settings=config.test_settings` -> PASS, no changes, 0 migrations.
  - `$env:PYTHONUTF8='1'; python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings` -> PASS, OpenAPI 3.0.3, fail-on-warn active.
  - `python manage.py test --settings=config.test_settings -v 1` -> PASS, 274 run, 268 non-skipped pass, 6 PostgreSQL-only skip, 0 fail, 0 error.
  - `python scripts/check_html_branding.py` -> PASS, `HTML_BRANDING_PASS files=220`.
  - stale live-summary scan -> PASS, 3 forbidden old live phrases absent.
  - capability trace scan -> PASS, 7 original requirement IDs and 17 stable capability groups present.
  - forbidden-term changed-diff scan -> PASS.
  - `git diff --name-status` -> PASS; only `BACKEND_SPEC.md` and `KARIZ_PROJECT_HANDOFF.md` modified.
  - Final `git diff --stat` -> PASS, exit 0; `BACKEND_SPEC.md | 53`, `KARIZ_PROJECT_HANDOFF.md | 668`, `2 files changed, 709 insertions(+), 12 deletions(-)`. Final `git diff --numstat` -> PASS, exit 0; `50 3 BACKEND_SPEC.md`, `659 9 KARIZ_PROJECT_HANDOFF.md`. Only non-failing LF-to-CRLF notices emitted.
- Self-correction loop:
  - score 1: `8/10`; old top V1-only target/out-of-target summary and old V4 resume point conflicted with C1-1.
  - fixes: top delivery target now states expanded Client-1 target with partial contracts; old scope sections are current-core history; old V4 next action is explicitly superseded.
  - score 2: `9/10`; source trace, target priority, fail-closed decisions, spec truth, scope boundary, and verification are consistent. No repository-controlled C1-1 defect remains.
- Assumptions: none about undefined business semantics. Priority is lowered only where the customer explicitly marked later/low/checkmarked work. Low priority means required last wave, not optional.
- External blockers: official provider documents/owners, target server/resources/domain/TLS, image digests, PostgreSQL/Compose/Nginx/browser proof, backup destination/schedule/retention/RPO/RTO/owner/restore proof, load target, scans, and UAT owners/data.
- Current Git commit: `bc0233fe815f93aa51a775b381c3885402d2c6bf`.
- Current git status: ` M BACKEND_SPEC.md`; ` M KARIZ_PROJECT_HANDOFF.md`; no other path listed.
- Commit: none created.

## 21. Sidebar hierarchy and future-module placeholders - 2026-08-11

### Result and scope

- Slice status: `DONE`; navigation structure only.
- Goal met: active Kariz sidebar now follows a grouped reference-style hierarchy while keeping the existing theme, colors, typography, RTL shell, layout, and CSS architecture.
- Backend implementation: none.
- Models, migrations, serializers, services, selectors, API endpoints, UI routes, JavaScript, and CSS: unchanged.
- Future modules use non-link `aria-disabled` placeholders or expandable group shells. No fake success and no dead `href="#"` control was added.

### Files inspected and changed

- Inspected: bounded sidebar section of `index.html`; `common/templates/common/base.html`; sidebar hooks in `common/static/common/kariz.css`; `setupNav()` in `common/static/common/kariz-app.js`; relevant navigation tests in `common/tests/test_auth_shell.py`, `test_sales_shell.py`, `test_commercial_shell.py`, and `test_ui.py`; current handoff and root Client-1 roadmap.
- Changed template: `common/templates/common/base.html` only.
- Changed test: `common/tests/test_auth_shell.py`.
- Changed documentation: `KARIZ_PROJECT_HANDOFF.md` and the root Client-1 roadmap.
- Unrelated templates, styles, scripts, routes, and application pages: unchanged.

### Sidebar hierarchy

1. `داشبورد` - future non-link placeholder.
2. `پروفایل` - real `/` profile route.
3. `فروشگاه` - expandable group shell:
   - `انبار` - future placeholder.
   - `حسابداری` - future placeholder.
   - `محصولات` - real `/products/` route.
   - `دسته‌بندی‌ها` - future placeholder.
4. `مرکز تماس` - expandable group shell:
   - `مشتریان` - real `/customers/` route.
   - `سرنخ‌ها` - real `/leads/` route retained.
   - `تماس‌ها` - real `/interactions/` route retained.
5. `فروش‌ها` - real `/sales/` route retained.
6. `فاکتورها` - future non-link placeholder.
7. `گزارش‌ها` - expandable group shell with real `/reports/user-performance/` child.
8. `امور مالی` - future non-link placeholder.
9. `کارهای روزانه` - future non-link placeholder.
10. `ارسال و تحویل` - future non-link placeholder.
11. `اهداف` - future non-link placeholder.
12. `اسناد` - future non-link placeholder.
13. `مدیریت سامانه` - role-gated expandable group retaining real ActivityLog and user-management routes.

### Future placeholder register and remaining backend work

| Requested module | Sidebar state | Remaining backend work before activation |
|---|---|---|
| Dashboard | Non-link placeholder | Approve dashboard metrics, role scope, refresh/as-of rules, selectors, API, page, and tests. |
| Profile | Real current route | Session inventory/revoke, avatar, and notification additions remain blocked; current own-profile edit stays live. |
| Store | Expandable shell | Store landing/summary contract and route are absent; Product child is live. |
| Inventory | Non-link placeholder | Warehouse, stock, movement, reservation, costing, concurrency, migration, API, and permissions are absent; `FINAL_WAVE_LOW`. |
| Accounting | Non-link placeholder | Accounting document/ledger/source-of-truth, roles, corrections, reconciliation, API, and reports are absent. |
| Products | Real current route | Category and expanded Product form remain blocked; current Product CRUD/deactivate stays live. |
| Categories | Non-link placeholder | Category schema, hierarchy/lifecycle, Product relation, scope, API, migration, and tests are absent. |
| Call Center | Expandable shell | Dedicated call-center dashboard, provider, duration/recording, consent, retention, and secure adapter are absent; Customer/Lead/manual Interaction children stay live. |
| Customers | Real current route | Classification, postcode contract, export, bulk work, document link, and 360 profile remain blocked. |
| Invoices | Non-link placeholder | Sale/Order/internal document/accounting Invoice meaning, lines, numbering, totals, tax, correction, migration, API, and permissions are absent. |
| Reports | Expandable shell | Current performance report is live; detailed drill-down and Client-1 SMS/contact/geography/postal/domain reports remain blocked. |
| Finance | Non-link placeholder | Payment, allocation, customer account, cheque, installment, receivable, profit/loss, reconciliation, API, and permissions are absent; advanced scope is `FINAL_WAVE_LOW`. |
| Daily Tasks | Non-link placeholder | Task/project/calendar/reminder entities, states, assignment, recurrence, notifications, API, and scope are absent. |
| Delivery | Non-link placeholder | Postal states/history, actor transitions, tracking, return/failure/cancel, provider choice, API, and report are absent. |
| Targets | Non-link placeholder | Sales-target entity, period, metric/formula, assignment, visibility, progress, API, and acceptance examples are absent. |
| Documents | Non-link placeholder | File storage, upload/download, scanner, type/size/version/retention, entity links, backup, scope, API, and tests are absent; `FINAL_WAVE_LOW`. |

### Authorization and safety

- Existing backend authorization did not change.
- Real links keep their current scoped routes and role guards.
- ActivityLog and user-management links stay inside the role-gated administration group.
- Future entries cannot navigate or submit. They are marked `aria-disabled="true"` where they are leaf placeholders.
- Expandable shells use native `details`/`summary`; no new script, plugin, or CSS selector exists.

### Verification and self-correction

- `python manage.py test common.tests.test_auth_shell common.tests.test_sales_shell common.tests.test_commercial_shell --settings=config.test_settings -v 1` -> PASS; 37 tests, 0 failures, 0 errors.
- `python manage.py test common.tests.test_auth_shell_browser --settings=config.test_settings -v 1` -> PASS; 2 headless Chrome tests, 0 failures, 0 errors. Safe live-server shutdown broken-pipe lines did not change `OK`.
- `python manage.py check --settings=config.test_settings` -> PASS; 0 issues.
- `python manage.py makemigrations --check --dry-run --settings=config.test_settings` -> PASS; no changes detected; 0 migrations created.
- `python scripts/check_html_branding.py` -> PASS; `HTML_BRANDING_PASS files=220`.
- `git diff --check` -> PASS; no whitespace error; only non-failing LF-to-CRLF working-copy notices.
- New navigation test proves all 16 requested module labels/data slots, hierarchy order, Store/Call Center/Reports/Administration expandable groups, real Profile/Product/Customer links, future placeholder markers, and absence of fake `href="#"` links.
- Self-correction score: `9/10`. The slice changes only sidebar hierarchy, keeps live route access, marks future work honestly, and introduces no backend or style drift.

### Remaining blocker and next phase

- [future module contracts]: Placeholder names do not approve business rules. Backend, route, and active page work stays blocked by the matching C1 decision register.
- [C1-2 gate]: Role, seat/capacity, Team, and after-sales workstream rules still not approved. Identity work cannot start.
- Exact next phase: C1-1 decision closure, then C1-2 preflight. Sidebar placeholders must stay non-operational until each module passes its own contract and implementation phase.
- Exact resume point: C1-1 decision closure, before any schema, model, migration, endpoint, UI route, or authorization edit.
- Exact next action: customer/business owner must resolve at least C1-DEC-GOV-001, SEAT-001, ROLE-001, TEAM-001, and AFTER-001 with an explicit role/workstream matrix. Then update C1-1 approvals and only after that start C1-2.
- Exact next implementation phase: `C1-2`, currently `BLOCKED_DECISION`. Do not start C1-2 from the supplied source alone.

## 22. Client-1 C1-2 preflight - blocked after C1-1 audit

- Request: check C1-1 and start C1-2 only if C1-1 is done.
- C1-1 audit result: reconciliation work is complete, but status is `BLOCKED_DECISION`; approved identity/workstream design does not exist.
- C1-2 status: `BLOCKED_DECISION`; phase not started.
- Blocking decisions: C1-DEC-GOV-001, C1-DEC-SEAT-001, C1-DEC-TEAM-001, and C1-DEC-AFTER-001. C1-DEC-ROLE-001 is resolved.
- Exact blocking facts:
  - final source says four fixed roles and later names only three; mapping/custody of `company_it` and `platform_admin` is unresolved;
  - no-seat-cap acceptance and real concurrency/load target are unresolved;
  - Sales Manager team boundary is unresolved;
  - after-sales operator/workstream identity and cross-panel visibility are unresolved.
- Fail-closed rule applied: no workstream/profile field, model, migration, default/backfill, permission helper, serializer, service, API, UI, navigation, or authorization change was invented.
- Files inspected: `AGENTS.md`, C1-1/C1-2 gate lines in `KARIZ_PROJECT_HANDOFF.md`, Client-1 scope/role blockers in `BACKEND_SPEC.md`, and the bounded C1-2 phase contract in the root Client-1 roadmap.
- Files changed in this preflight: `KARIZ_PROJECT_HANDOFF.md` only for this blocker checkpoint.
- Existing uncommitted C1-1 files preserved: `BACKEND_SPEC.md` and `KARIZ_PROJECT_HANDOFF.md`.
- Migrations: none.
- API endpoints changed: none.
- UI routes changed: none.
- Authorization impact: none.
- Tests: not rerun; no source or behavior changed. Prior C1-1 full gate remains PASS: 274 run, 268 non-skipped pass, 6 skip, 0 fail, 0 error.
- Exact commands executed:
  - `git rev-parse HEAD` -> PASS, exit 0, `bc0233fe815f93aa51a775b381c3885402d2c6bf`.
  - `git status --short` -> PASS, exit 0; ` M BACKEND_SPEC.md`, ` M KARIZ_PROJECT_HANDOFF.md`.
  - ordered authority read and bounded `rg` checks for C1-1 status/start gate/decision IDs/spec blockers -> PASS; confirmed blockers above.
  - bounded C1-2 roadmap read -> PASS; phase explicitly requires approved identity design and fail-closed stop otherwise.
  - post-checkpoint `git diff --check` -> PASS, exit 0; no whitespace errors, only non-failing LF-to-CRLF notices.
- Assumptions: none.
- Repository state modified by preflight: handoff documentation only; no functional implementation.
- Current Git commit: `bc0233fe815f93aa51a775b381c3885402d2c6bf`.
- Current git status: ` M BACKEND_SPEC.md`; ` M KARIZ_PROJECT_HANDOFF.md`.
- Self-correction score: `9/10`; phase gate is explicit, current repository behavior is preserved, and no unsafe identity rule was inferred.
- Exact resume point: C1-1 decision closure before C1-2.
- Exact next action: approve the four blocking decisions with an explicit role/workstream/visibility matrix and seat-cap/capacity rule; then update C1-1 status and rerun this C1-2 preflight.

## 23. Controlled implementation baseline - 2026-08-11

### Assessment boundary and result

- Assessment status: `DONE`; documentation only.
- Repository start point: commit `31329cfbf74fef8ab17645a14f9ad8d297b2a26e`; working tree clean before this assessment.
- Read scope: `BACKEND_SPEC.md`, this handoff, the root Client-1 roadmap, and only the relevant first-party Django app code, tests, active templates, and connected client file listed below.
- Change scope: this handoff and the root Client-1 roadmap only.
- Functional code, model, migration, endpoint, UI route, authorization, architecture, and UI style change: none.
- Baseline verdict: the current Core V1 is a real connected modular Django/DRF implementation. The expanded Client-1 target is not implemented. C1-2 remains fail-closed until its identity and workstream decisions are approved.

### Files inspected

- Authority and phase documents: `BACKEND_SPEC.md`, `KARIZ_PROJECT_HANDOFF.md`, and the root Client-1 roadmap.
- Accounts: `accounts/access.py`, `models.py`, `permissions.py`, `serializers.py`, `services.py`, `auth_urls.py`, `urls.py`, `views.py`; bounded test-name inspection in `accounts/tests/test_accounts.py` and `test_bootstrap_platform_admin.py`; migration manifest `0001_initial.py` and `0002_user_role_constraint.py`.
- Sales core: `sales/models.py`, `selectors.py`, `serializers.py`, `services.py`, `urls.py`, `views.py`; bounded test-name inspection in `sales/tests/test_workflows.py`, `test_scope_attacks.py`, and `test_migration_preflights.py`; migration manifest `0001_initial.py` through `0010_interaction_contract.py`.
- Reports: `reports/selectors.py`, `serializers.py`, `services.py`, `urls.py`, `views.py`, `xlsx.py`; bounded test-name inspection in `reports/tests/test_user_performance.py`.
- Audit: `auditlog/models.py`, `permissions.py`, `selectors.py`, `serializers.py`, `services.py`, `urls.py`, `views.py`; bounded test-name inspection in `auditlog/tests/test_api.py` and `test_services.py`; migration manifest `0001_initial.py` and `0002_activitylog_role_snapshots.py`.
- Active application layer: `common/permissions.py`, `views.py`, `viewsets.py`, `ui_urls.py`, `ui_views.py`, `common/static/common/kariz-app.js`; bounded test-name inspection in `common/tests/test_auth_shell.py`, `test_sales_shell.py`, `test_commercial_shell.py`, `test_system_api.py`, and `test_query_growth.py`.
- Active templates: every one of the 19 files under `common/templates/common/`: `base.html`, `error.html`, `home.html`, `login.html`; list/detail templates for users, customers, leads, interactions, products, sales, and activity logs; `reports/user_performance.html`.
- Deliberately not inspected: parent/vendor archive, forbidden dependency/media/build trees, unrelated demo pages, secrets, review bundle, code-dumper output, and unrelated Django/operations files.

### 1. Existing completed modules

| Module | Current implemented baseline | Current proof boundary |
|---|---|---|
| Identity and accounts | Custom `User`; four fixed CRM roles; clean CRM identity excludes staff, superuser, groups, and direct permissions; login/logout/me; own-profile edit; controlled user create/edit/deactivate; dedicated role change; last active Platform Admin guard. | Repository tests exist. Three-role Client-1 wording, sessions, avatar, notifications, export, team, and workstream are not implemented. |
| Customer | Scoped create/list/retrieve/patch/search/order/page; safe deactivation; national ID, email, province, city, address, notes; server-owned creator/active/timestamps. | Core is connected. Category, postcode contract, document link, export, bulk actions, merge, and 360 view are absent. |
| CustomerPhone | Many phones per Customer; Iranian normalization; global active normalized-phone uniqueness; one active primary phone; scoped create/edit/deactivate; Customer cannot be moved. | Core is connected. Shared-number override/import rules are not approved. |
| Lead | Scoped create/list/retrieve/permitted patch; source, campaign/batch, interested Product, follow-up, notes; manual assignment/reassignment; append-only assignment history; safe audit. | Current raw status can be shown/filtered, but final enum/transitions, auto-assignment, Team, priority, archive, conversion, Opportunity, and Pipeline are absent. |
| Interaction | Manual inbound/outbound append-only contact entry tied to an authorized Lead; server-derived Customer/agent; occurred/follow-up time, phone, outcome, notes. | Core is connected. Final outcome groups, contact status, timeline, task/calendar/reminder, specialist report, recording, and telephony are absent. |
| Product | SKU, name, positive current price, description, active flag, creator/updater; search/order/page; elevated create/edit/deactivate; Sales Agent active read-only. | Core is connected. Category, variant, inventory, costing, multi-price, discount, and profit are absent. |
| Sale | Authorized creation from Lead; Product/current-price snapshot when Product is supplied; direct `total_amount` is accepted only when Product is absent; quantity and total integrity; server-derived Customer/seller/status; confirmed/cancelled states; elevated dedicated cancel; no hard delete or guessed correction. | Operational Sale only. Order, quotation, legal/accounting Invoice, Payment, postal flow, and PDF are absent. API can accept optional `sold_at`; connected UI requires Product and sends only Lead, Product, quantity, and notes. |
| Reporting | One predefined user-performance projection with four exact metrics; inclusive start/exclusive end; optional user and Product filters; same query for JSON/XLSX; safe spreadsheet text and stable columns. | No detailed drill-down, contact-status, city/province, postal, SMS, domain, profit/loss, receivable, PDF, or dynamic report. |
| Audit and platform guard | Append-oriented safe `ActivityLog`; request ID and bounded IP; safe allowlisted changes; Company IT hides platform-level rows; Platform Admin sees all; live and database-ready health split; strict query keys. | Repository behavior exists. Target runtime, alerting, anomaly detection, and external operations proof remain open. |
| Active Persian UI | Same-origin CSRF client and 19 maintained Persian RTL templates for auth/profile, users, Customer/phones, Leads/assignment history, Interactions, Products, Sales, performance/XLSX, and ActivityLog. | Connected local shell exists. It is not Client-1 full dashboard or target-site proof. |

### 2. Existing API baseline

All paths below are under `/api/v1/`, use the established session/CSRF and error/request-ID contract, and use trailing slash where shown.

| API family | Existing methods/actions |
|---|---|
| Auth | `POST auth/login/`; `POST auth/logout/`; `GET/PATCH auth/me/`. |
| Users | `GET/POST users/`; `GET/PATCH users/{id}/`; `POST users/{id}/change-role/`; no delete route. |
| Customers | `GET/POST customers/`; `GET/PATCH customers/{id}/`; `POST customers/{id}/deactivate/`; search, order, page. |
| Customer phones | `GET/POST customer-phones/`; `GET/PATCH customer-phones/{id}/`; `POST customer-phones/{id}/deactivate/`; exact scoped `customer` filter. |
| Leads | `GET/POST leads/`; `GET/PATCH leads/{id}/`; `GET leads/assignees/`; `GET leads/{id}/assignment-history/`; `POST leads/{id}/reassign/`; exact raw `status` filter. |
| Interactions | `GET/POST interactions/`; `GET interactions/{id}/`; append-only, no patch/delete route. |
| Products | `GET/POST products/`; `GET/PATCH products/{id}/`; `POST products/{id}/deactivate/`; writes require elevated role. |
| Sales | `GET/POST sales/`; `GET sales/{id}/`; `POST sales/{id}/cancel/`; exact confirmed/cancelled status filter; no patch/delete route. Create accepts optional Product, direct amount only without Product, and optional `sold_at`; the maintained UI uses Product and omits amount/time. |
| Reports | `GET reports/user-performance/`; `GET exports/user-performance.xlsx`; same required period and optional user/Product filters. |
| Audit | `GET activity-logs/`; `GET activity-logs/{id}/`; read-only. |
| Health | `GET health/live/`; `GET health/ready/`; readiness checks the database. |

Not present: any Client-1 API for after-sales, sessions, notifications, Customer export/bulk/360, Lead transition/pipeline, tasks/calendar, inventory, documents/invoices, postal history, finance, SMS, files, global search/import, automation, integrations, PWA, anomaly workflow, detailed drill-down, or new grouped reports.

### 3. Existing template baseline

| Template group | Files and live purpose |
|---|---|
| Shell/auth | `base.html` real navigation/logout; `login.html` session login; `home.html` own profile; `error.html` safe Persian error page. |
| Users | `users/list.html` scoped directory and create dialog; `users/detail.html` edit, role change, and deactivate controls. |
| Customers | `customers/list.html` search/order/page and create; `customers/detail.html` edit, phone list/create/edit/deactivate, and elevated Customer deactivate. |
| Leads | `leads/list.html` search/status/order/page and create; `leads/detail.html` scoped edit, assignee selection, reassignment, and assignment history. |
| Interactions | `interactions/list.html` search/order/page and manual create; `interactions/detail.html` read-only detail. |
| Products | `products/list.html` search/order/page and elevated create; `products/detail.html` read-only for agent and edit/deactivate for elevated roles. |
| Sales | `sales/list.html` search/status/order/page and create; `sales/detail.html` read-only snapshots and elevated cancel. |
| Reports | `reports/user_performance.html` period/user/Product filters, result table, and XLSX link. |
| Audit | `activity_logs/list.html` scoped search/order/page; `activity_logs/detail.html` read-only safe event detail. |

No maintained active template exists for the missing Client-1 modules. Demo/template shells outside this list are not implementation evidence.

### 4. Existing permission baseline

| Capability | Sales Agent | Sales Manager | Company IT | Platform Admin |
|---|---|---|---|---|
| Login and own profile | Yes | Yes | Yes | Yes |
| User directory/admin | No | No; fail closed until Team rule | Yes, but Platform Admin rows/role grants hidden | Yes |
| Customer read/edit | Own-created or linked to assigned Lead | Company scope | Company scope | Company scope |
| Customer deactivate | No | Yes | Yes | Yes |
| CustomerPhone write/deactivate | Inside scoped Customer | Company scope | Company scope | Company scope |
| Lead read | Assigned, plus own-created unassigned | Company scope | Company scope | Company scope |
| Lead edit/Interaction/Sale create | Assigned Lead only | Company scope | Company scope | Company scope |
| Lead reassignment | No | Yes, only to active clean Sales Agent | Yes, same | Yes, same |
| Product read | Active only | All | All | All |
| Product write/deactivate | No | Yes | Yes | Yes |
| Sale read | Own sales only | Company scope | Company scope | Company scope |
| Sale cancel | No | Yes | Yes | Yes |
| Performance report | Own row only | All clean CRM user rows | All clean CRM user rows | All clean CRM user rows |
| ActivityLog | No | No | Scoped; platform rows hidden | All rows |

Common rules: only active clean CRM identities pass; server-owned identity, role, ownership, assignment, snapshot, status, and audit fields are blocked; direct out-of-scope IDs are masked by scoped querysets; sensitive actions are throttled; historical records use deactivate/cancel or append-only behavior instead of normal hard delete.

Known deliberate fail-closed gaps: Sales Manager user administration is denied because Team scope is not defined; Sales Manager audit is denied because the limited operational audit boundary is not defined; no after-sales workstream permission exists. The later direct User Management instruction confirms the existing four fixed CRM roles and supersedes the earlier three-label ambiguity for this boundary.

### 5. Missing Client-1 requirements

#### Original seven

| ID | Current coverage | Missing contract or implementation | State |
|---|---|---|---|
| C1-REQ-001 sales panel/no seat cap | Core sales shell exists; no hard-coded seat cap found in inspected apps. | Exact licensing wording, role/workstream/team matrix, panel acceptance list, peak concurrency, load target, and UAT. | `BLOCKED_DECISION` |
| C1-REQ-002 after-sales panel/no seat cap | No after-sales model, service, API, permission, route, or maintained template. | Operator identity, case schema, Customer/Document link, assignment, states/transitions, manager scope, lifecycle, audit, capacity, and UAT. | `BLOCKED_DECISION` |
| C1-REQ-003 detailed performance/drill-down | Four summary metrics and XLSX exist. | New metrics and denominators, drill-down rows, reassignment/cancel rules, timezone/calendar, bounds, access, sample totals, and UI/API/XLSX parity. | `BLOCKED_DECISION` |
| C1-REQ-004 inbound SMS by day/hour | No SMS entity, secure receipt boundary, provider adapter, or report. Manual inbound Interaction is not SMS. | Provider docs, auth/signature, replay/idempotency, retained fields/body policy, received time, grouping timezone/calendar, scope, and samples. | `BLOCKED_DECISION`; live adapter `BLOCKED_EXTERNAL` |
| C1-REQ-005 document count by city/province | Customer has current city/province; Sale exists. No approved counted document or historical geography snapshot/report. | Sale versus internal Document/Order/Invoice, line/number/state rules, snapshot source, date basis, null rules, scope, sample totals. | `BLOCKED_DECISION` |
| C1-REQ-006 incoming number by contact status | Phone, Lead, and free-text Interaction outcome exist. No approved counted unit/status derivation/report. | Unit/source, dedupe window, status list, no-contact/latest tie-break, date basis, filters, scope, drill-down/export, samples. | `BLOCKED_DECISION` |
| C1-REQ-007 document count by postal status | No document/postal model, history, transition service, tracking, provider, or report. | Document source, registered meaning, state table/transitions, actor, history/current grouping, return/failure/cancel, date basis, scope, samples. | `BLOCKED_DECISION` |

#### Expanded target gaps

- Accounts: session inventory/revocation, avatar, notifications, user export, approved Team, and approved sales/after-sales workstream.
- Customer: classification, postcode contract, document relationship, export, bounded bulk operations, merge policy, and 360 profile/activity.
- Lead/contact: final state machine, initial assignment, priority/archive/conversion, Opportunity/Pipeline, unified timeline, meetings/tasks/projects/calendar/reminders, and manual specialist report contract.
- Product/inventory: category and expanded form; Warehouse, stock movements, purchase cost, multi-price, discount, valuation, profit, and inventory reports in `FINAL_WAVE_LOW`.
- Commercial/finance: Order, internal document, quotation, accounting Invoice, line items, numbering, geography snapshot, postal workflow, Payment, ledger/customer account, cheque, installment, receivable, profit/loss, and operational PDF. Full financial set is `FINAL_WAVE_LOW`.
- Reports: detailed drill-down, dashboard, contact/SMS/geography/postal/domain reports, P&L/receivable, PDF, and bounded dynamic report builder.
- Collaboration/communications/files: activity timeline, calendar/task/project/reminder, provider-backed SMS/email/telephony, operational files, scanner/storage/version/retention/download policy.
- Search/data: global search, saved filters, and bounded bulk XLSX import in `FINAL_WAVE_LOW`.
- Platform/late: workflow automation, dynamic permission conflict resolution, website/store/gateway/accounting integrations, installable web application behavior, abnormal-activity detection, and full active-UI hardening.
- Runtime: native PostgreSQL, Compose/Nginx/TLS, exact release browser proof, real scheduled backup plus isolated restore, load/scan, target deployment, UAT, and cutover evidence.

### 6. Recommended implementation order

1. Decision closure: approve governance, no-seat-cap/capacity, Team boundary, and sales/after-sales workstream visibility. The later direct User Management instruction fixes the role count at the existing four roles. No workstream schema change before the remaining gate.
2. C1-2 identity/operator separation: additive workstream design, migration/backfill, service/selector permission reuse, user admin, UI, and full role/workstream tests.
3. C1-3 minimum operational document/geography/postal base: only after document, geography, and postal contracts are approved.
4. C1-4 contact-status and detailed performance: only after counted unit, status derivation, formulas, drill-down, and time rules are approved.
5. C1-5 after-sales: only after case schema, states, assignment, Customer/Document relation, and scope are approved.
6. C1-6 inbound SMS: provider-neutral core/report after data contract; live adapter only from official provider security docs.
7. Approved normal-priority additions: Product category/form, Lead state/pipeline, collaboration/timeline, notifications, domain reports, PWA/anomaly work in dependency order set by C1-DEC-DELIVERY-001.
8. `FINAL_WAVE_LOW`: Inventory/pricing/profit; full quotation/accounting/finance; files; global search/saved filters/XLSX import; PDF/dynamic reports; checked commerce/accounting integrations.
9. C1-7 unified dashboard/navigation and active-UI hardening over implemented capabilities only.
10. C1-8 production-like runtime proof, then C1-9 target deployment/UAT/cutover for the exact release.

### Findings, blockers, and exact next phase

- Finding: app structure already uses models, selectors, serializers, services, viewsets, constraints, audit, and tests in a coherent modular monolith. No architecture change is needed for the next approved additive slice.
- Finding: active templates call real `/api/v1/` endpoints through the same-origin CSRF client. No missing Client-1 feature may be claimed from unrelated demo HTML.
- Finding: current role scope is fail-closed where Team, manager audit, and after-sales rules are missing.
- C1-DEC-ROLE-001 current User Management resolution: four fixed role codes remain authoritative; the existing Company IT and Platform Admin privilege boundary, grant custody, last-admin guard, audit visibility, and inactive-session behavior remain unchanged. Team and after-sales workstream rules are separate open decisions.
- [C1-DEC-SEAT-001]: No app seat cap seems present. Capacity and load rule still unknown.
- [C1-DEC-TEAM-001]: Team bound not set. Manager scope blocked.
- [C1-DEC-AFTER-001]: After-sales user and case flow not set. C1-2 and C1-5 blocked.
- [C1-DEC-DOC-001, C1-DEC-GEO-001, C1-DEC-POST-001]: Document and postal truth not set. C1-3 and two reports blocked.
- [C1-DEC-CONTACT-001, C1-DEC-INCOMING-001, C1-DEC-PERF-001]: Contact unit, state, and report math not set. C1-4 blocked.
- [C1-DEC-SMS-001]: Provider and safe receive rule not set. C1-6 live work blocked.
- [C1-DEC-RUNTIME-001]: Target host, TLS, backup, load, and owner data absent. Release proof blocked.
- Exact next phase: `C1-1 decision closure`, not feature build.
- Exact next action: get an explicit future Team/after-sales workstream/visibility matrix plus no-seat-cap/capacity rule for C1-DEC-GOV-001, SEAT-001, TEAM-001, and AFTER-001. Update approvals. Then rerun C1-2 preflight without changing the four fixed role codes.

### Assessment change and verification record

- Files changed: `KARIZ_PROJECT_HANDOFF.md` and the root Client-1 roadmap.
- Migrations: none created or changed.
- API endpoints: none created or changed.
- UI routes/templates/styles: none created or changed.
- Authorization: none changed.
- Tests and checks:
  - `python manage.py check --settings=config.test_settings` -> PASS; 0 issues.
  - `python manage.py makemigrations --check --dry-run --settings=config.test_settings` -> PASS; no changes detected; 0 migrations created.
  - `python manage.py test accounts.tests.test_accounts sales.tests.test_workflows sales.tests.test_scope_attacks reports.tests.test_user_performance auditlog.tests.test_api auditlog.tests.test_services common.tests.test_auth_shell common.tests.test_sales_shell common.tests.test_commercial_shell common.tests.test_system_api common.tests.test_query_growth --settings=config.test_settings -v 1` -> PASS; 142 tests, 0 failures, 0 errors.
  - active-template manifest check -> PASS; 19 maintained templates under `common/templates/common/`.
  - baseline section/roadmap gate scan -> PASS; section 21, all six requested baseline parts, current roadmap baseline, and C1-1 decision-closure instruction found.
  - `git diff --check` -> PASS; no whitespace error; only non-failing LF-to-CRLF working-copy notices.
- Self-correction loop, score 1: `8/10`.
- [Sale API baseline]: First draft did not state Product-less direct amount or optional `sold_at`. API and UI write boundary could blur.
- [assessment evidence]: Verification record was pending. Baseline proof was not closed.
- Fix: exact Sale API/UI boundary recorded; Django check, migration drift, 142 focused tests, template count, section/gate scan, and diff check passed.
- Self-correction loop, score 2: `9/10`. Core architecture/code quality is strong for implemented scope; baseline is complete and honest; Client-1 feature coverage stays separately blocked and is not hidden by this score.
- Current Git commit: `31329cfbf74fef8ab17645a14f9ad8d297b2a26e`.
- Current git status: only the root Client-1 roadmap and `KARIZ_PROJECT_HANDOFF.md` modified by this documentation assessment.
- Commit: none created.

## 24. Client-1 User Management completion - 2026-08-11

### Result

- Requested boundary: `DONE`.
- Existing production behavior already implemented login, logout, current-profile read/edit, user list/detail, create, edit, inactive-state deactivation/reactivation, dedicated role change, fixed role validation, backend authorization, safe audit, and last active Platform Admin protection.
- Completion work added focused acceptance proof for the uncovered delete, inactive-session, permission-isolation, and escalation paths. No duplicate endpoint, service, model, or UI control was added.
- The direct role list in this request confirms `sales_agent`, `sales_manager`, `company_it`, and `platform_admin`. It supersedes the earlier three-label ambiguity for current User Management.

### Files inspected and changed

- Authority/status inspected: `BACKEND_SPEC.md`, `KARIZ_PROJECT_HANDOFF.md`, and the root Client-1 roadmap.
- Backend inspected: `accounts/access.py`, `models.py`, `permissions.py`, `serializers.py`, `services.py`, `views.py`; `common/serializers.py`, `viewsets.py`; `auditlog/services.py`.
- Active application inspected: `common/templates/common/login.html`, `home.html`, `users/list.html`, `users/detail.html`; bounded user/auth handlers in `common/static/common/kariz-app.js`.
- Tests inspected: `accounts/tests/test_accounts.py`, `common/tests/test_auth_shell.py`, and `common/tests/test_auth_shell_browser.py`.
- Changed for this slice: `accounts/tests/test_accounts.py`, `KARIZ_PROJECT_HANDOFF.md`, and the root Client-1 roadmap.
- Templates, client script, styles, models, migrations, serializers, services, views, routes, and architecture changed for this slice: none.
- Pre-existing sidebar changes in `common/templates/common/base.html` and `common/tests/test_auth_shell.py` were preserved and verified; they were not widened by this slice.

### Endpoint and behavior baseline

- `POST /api/v1/auth/login/`: session login for active clean CRM identities only; CSRF and login throttle remain enforced.
- `POST /api/v1/auth/logout/`: authenticated session logout; CSRF remains enforced.
- `GET/PATCH /api/v1/auth/me/`: current profile read and bounded own-profile edit; role, username, active state, and server identity fields stay protected.
- `GET/POST /api/v1/users/`: scoped user list and default Sales Agent creation.
- `GET/PATCH /api/v1/users/{id}/`: scoped detail, profile-field edit, password change, deactivate, and reactivate.
- `POST /api/v1/users/{id}/change-role/`: dedicated fixed-role transition.
- `DELETE /api/v1/users/{id}/`: unavailable with HTTP 405; the user row remains. Historical identity uses `is_active=False`.
- Deactivation writes a safe `user.updated` ActivityLog entry containing only the changed field name and password-change boolean. Passwords and private payloads are not stored.
- Migrations: none created or changed.

### Backend authorization matrix

| Action | Sales Agent | Sales Manager | Company IT | Platform Admin |
|---|---:|---:|---:|---:|
| Login/logout/current profile | Yes | Yes | Yes | Yes |
| User list/detail | No | No; Team scope undefined | Yes, excluding Platform Admin | Yes |
| Create/edit/deactivate/reactivate | No | No | Yes, non-platform targets | Yes |
| Grant Sales Agent/Manager/Company IT | No | No | Yes | Yes |
| Grant or manage Platform Admin | No | No | No | Yes |
| Hard delete user | No | No | No | No |

- Backend permission and scoped queryset checks are authoritative. UI visibility is only presentation.
- Staff, superuser, Django-group, and direct-permission identities remain outside CRM identity scope.
- Inactive users lose current session/API access immediately and cannot log in again until an authorized reactivation.
- Company IT escalation is rejected both when `role` is smuggled through general PATCH and when Platform Admin is requested through the dedicated action.

### Tests and verification

- `python manage.py test accounts.tests.test_accounts.AccountSecurityTests --settings=config.test_settings -v 1` -> PASS; 28/28.
- `python manage.py test accounts.tests common.tests.test_auth_shell common.tests.test_auth_shell_browser --settings=config.test_settings -v 1` -> PASS; 61/61. Non-failing live-server broken-pipe shutdown lines did not change `OK`.
- `python manage.py test --settings=config.test_settings -v 1` -> PASS; 279 run, 273 pass, 6 skip, 0 failure, 0 error.
- `python manage.py check --settings=config.test_settings` -> PASS; 0 issues.
- `python manage.py makemigrations --check --dry-run --settings=config.test_settings` -> PASS; no changes detected.
- `python -X utf8 manage.py spectacular --validate --fail-on-warn --settings=config.test_settings` -> PASS; schema valid with no warning. Initial default-code-page output failed only while printing Persian schema text; UTF-8 rerun passed.
- `python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0` -> PASS.
- `node --check common/static/common/kariz-app.js` -> PASS.
- `python scripts/check_html_branding.py` -> PASS; `HTML_BRANDING_PASS files=220`.
- `git diff --check` -> PASS; no whitespace error; only non-failing LF-to-CRLF working-copy notices.
- `git diff --stat` -> PASS; cumulative working tree has 5 modified files, including preserved earlier sidebar work. This User Management slice changes one test file plus the two requested documents.

### Self-correction loop

- Score 1: `8/10`.
- [user deletion proof]: No direct acceptance test proved DELETE 405 and row survival. No-delete rule could regress unseen.
- [inactive user proof]: Existing tests split inactive access and audit. One full deactivation/session/login proof was absent.
- [role access proof]: Existing checks covered parts. Sales-role admin denial and both Company IT escalation paths lacked one explicit completion gate.
- [handoff structure]: New sections had wrong order and one C1-2 checkpoint was nested under sidebar work. Resume path could mislead.
- Fix: added four focused account security tests; corrected handoff heading order; recorded the direct four-role decision and remaining separate blockers.
- Score 2: `9/10`. Implementation, authorization, audit, inactive-state lifecycle, no-delete behavior, and regression proof now match the requested boundary without architecture or UI drift.

### Blockers and next phase

- Blockers for requested User Management boundary: none.
- [Team scope]: Sales Manager user administration stays denied. Team member and company-wide exception rules still absent.
- [after-sales workstream]: Operator identity and cross-workstream access still absent. Broad C1-2 stays blocked.
- [account additions]: Session inventory/revoke, avatar, notifications, and user export lack approved contracts. Not part of this completion.
- Next recommended phase: close C1-DEC-GOV-001, C1-DEC-SEAT-001, C1-DEC-TEAM-001, and C1-DEC-AFTER-001, then rerun C1-2 preflight while preserving the four fixed role codes.
- Current Git commit at verification start: `31329cfbf74fef8ab17645a14f9ad8d297b2a26e`.
- Commit: none created.

## 25. Client-1 Customer Management completion - 2026-08-11

### Result and safe contract

- Requested Customer Management boundary: `DONE`.
- Existing `full_name` remains the name field to preserve existing clients. Added blank-safe `postal_code` and `category` fields without making old payloads invalid.
- `postal_code` is bounded opaque text up to 32 characters. No country-specific format, normalization, or reporting meaning was invented.
- `category` is a bounded plain-text label up to 100 characters. No category entity, hierarchy, fixed choices, ownership, or lifecycle was invented.
- Customer responses add a read-only active `primary_phone` projection. Existing nested initial phone create and full CustomerPhone endpoints remain unchanged.
- Existing CustomerPhone label, Iranian normalization, global active normalized-number uniqueness, one active primary phone per Customer, ownership guard, and inactive-state history remain unchanged.
- The maintained Customer detail page is now a real profile with paged related Leads, Interactions, and Sales inside the actor's existing backend scopes.
- No Customer or CustomerPhone hard-delete route or control exists. The existing dedicated deactivate actions remain authoritative.

### Files inspected

- Authority/status: `BACKEND_SPEC.md`, `KARIZ_PROJECT_HANDOFF.md`, and the root Client-1 roadmap.
- Customer backend: `sales/models.py`, `selectors.py`, `serializers.py`, `services.py`, `views.py`, `urls.py`; migration manifest `sales/migrations/0001_initial.py` through `0010_interaction_contract.py`.
- Active application: `common/ui_views.py`, `ui_urls.py`, `viewsets.py`, `serializers.py`, `common/static/common/kariz-app.js`, `common/templates/common/customers/list.html`, and `detail.html`.
- Tests: relevant bounded sections of `sales/tests/test_workflows.py`, `test_scope_attacks.py`, `common/tests/test_sales_shell.py`, `test_sales_shell_browser.py`, `test_system_api.py`, and `test_query_growth.py`.
- Backend documentation: `docs/backend/ENTITY_CATALOG.md`, `API_CONTRACT.md`, `RELATIONSHIPS.md`, and `ERD.mmd`.
- Not inspected: vendor/demo/media/build/dependency trees, secrets, review bundle, and code-dumper output.

### Files changed

- Contract/status: `BACKEND_SPEC.md`, `KARIZ_PROJECT_HANDOFF.md`, and the root Client-1 roadmap.
- Entity/API documentation: `docs/backend/ENTITY_CATALOG.md` and `docs/backend/API_CONTRACT.md`.
- Backend: `sales/models.py`, `services.py`, `serializers.py`, `views.py`, and new migration `sales/migrations/0011_customer_profile_fields.py`.
- Active UI: `common/templates/common/customers/list.html`, `common/templates/common/customers/detail.html`, and `common/static/common/kariz-app.js`.
- Tests: `sales/tests/test_workflows.py`, `common/tests/test_sales_shell.py`, `common/tests/test_sales_shell_browser.py`, and `common/tests/test_system_api.py`.
- Styles, shell layout, architecture, roles, existing route names, and existing field names: unchanged.

### Migration and API

- Migration: `sales.0011_customer_profile_fields` adds nullable-by-blank-semantics `category` and `postal_code` CharFields with empty-string defaults at the model/API boundary. It has no data rewrite, deletion, or relation change.
- Existing `GET/POST /api/v1/customers/` and `GET/PATCH /api/v1/customers/{id}/` remain compatible. Responses add `postal_code`, `category`, and read-only `primary_phone`; old create/update payloads still work.
- Existing search now also covers province, city, postal code, category, address, and normalized phone.
- Existing `POST /api/v1/customers/{id}/deactivate/` remains unchanged. `DELETE` remains HTTP 405.
- Existing `customer-phones/` and `customer-phones/{id}/deactivate/` contracts remain unchanged.
- New `GET /api/v1/customers/{id}/leads/`: paginated related Leads.
- New `GET /api/v1/customers/{id}/interactions/`: paginated related Interactions.
- New `GET /api/v1/customers/{id}/sales/`: paginated related Sales.
- New related routes accept only `page` and `format`; unknown query keys fail with HTTP 400.

### Authorization and UI

- Customer direct ID is resolved through `customers_for(actor)` first. Out-of-scope IDs return 404 for detail and all three related routes.
- Each related route then applies `leads_for(actor)`, `interactions_for(actor)`, or `sales_for(actor)`. A visible Customer does not grant wider related-record access.
- Sales Agent keeps own/assigned Customer scope and existing relation-specific scope. Sales Manager, Company IT, and Platform Admin keep existing company operational scope.
- Customer deactivation remains limited to Sales Manager, Company IT, and Platform Admin. Sales Agent cannot deactivate.
- `primary_phone`, normalized number, creator, active state, and timestamps are server-owned in Customer payloads.
- Persian RTL create/edit forms now include postal code and category. Customer list adds primary phone, category, and postal code. Detail adds paged related tables using existing table/card/button classes.
- Existing danger-zone button says deactivate and calls the real deactivate endpoint. No delete button, fake success, new CSS, layout replacement, or theme change exists.

### Tests and evidence

- New backend proof covers: new field create/read/update/search, old payload compatibility, length guard, primary-phone projection, server-field rejection, related pagination, relation scope, out-of-scope 404, and unknown-query rejection.
- Existing and retained proof covers: phone label, normalization, Unicode bypass rejection, global active duplicate prevention, one active primary phone, phone owner immutability, phone/customer deactivate, no DELETE, direct-ID masking, and four-role scope.
- New UI proof covers: create/edit fields, three relation sections, deactivate-only control, and real desktop browser data for postal code, category, Lead, Interaction, and Sale rows.
- `python manage.py test sales.tests.test_workflows.CoreWorkflowTests common.tests.test_sales_shell common.tests.test_system_api common.tests.test_query_growth --settings=config.test_settings -v 1` -> PASS; 72/72.
- `python manage.py test common.tests.test_sales_shell_browser --settings=config.test_settings -v 1` -> PASS; 2/2. Non-failing live-server broken-pipe shutdown lines did not change `OK`.
- `python manage.py test --settings=config.test_settings -v 1` -> PASS; 282 run, 276 pass, 6 skip, 0 failure, 0 error.
- `python manage.py check --settings=config.test_settings` -> PASS; 0 issues.
- `python manage.py makemigrations --check --dry-run --settings=config.test_settings` -> PASS; no changes detected beyond committed migration state.
- `python manage.py sqlmigrate sales 0011 --settings=config.test_settings` -> PASS; SQL proof copies every existing row with `''` for both new non-null text columns and preserves IDs/relations.
- `python -X utf8 manage.py spectacular --validate --fail-on-warn --settings=config.test_settings` -> PASS; schema valid, no warning.
- `python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0` -> PASS.
- `node --check common/static/common/kariz-app.js` -> PASS.
- `python scripts/check_html_branding.py` -> PASS; `HTML_BRANDING_PASS files=220`.
- `git diff --check` -> PASS; no whitespace error; only non-failing LF-to-CRLF working-copy notices.
- `git diff --stat` -> PASS; 16 tracked modified paths plus the new untracked migration file. No unrelated dirty file existed at task start.

### Self-correction loop

- Score 1: `8/10`.
- [primary phone schema]: Runtime projection worked, but first schema saw it as string. Generated client contract was wrong.
- [customer detail load]: First page version fired five database reads together. Live browser test exposed a connection failure and hidden page.
- Fix: added an explicit nullable primary-phone schema component; changed profile fetches to stable sequential reads; extended real browser proof across all related sections.
- Score 2: `9/10`. Additive migration, backward-compatible API, scoped relation reads, real RTL profile, phone integrity, deactivate-only lifecycle, and regression proof now meet this slice without style or architecture drift.

### Assumptions, blockers, and next phase

- Assumption: because no taxonomy was supplied, `category` is a plain optional label, not a new entity. This is the smallest backward-compatible implementation of the direct request.
- Assumption: because no postal format was supplied, `postal_code` preserves bounded user text and does not silently normalize or reject country-specific forms.
- Blockers for the requested Customer Management boundary: none.
- [category governance]: Fixed categories, hierarchy, merge, and lifecycle not set. Plain label works; governed taxonomy waits.
- [postal governance]: Country format, normalization, and report snapshot rules not set. Current field stores bounded text only.
- [customer expansion]: Document relation, export, bounded bulk operations, and merge rules not set. They remain outside this slice.
- Next recommended phase: close C1-DEC-GOV-001, C1-DEC-SEAT-001, C1-DEC-TEAM-001, and C1-DEC-AFTER-001 before broad C1-2; close document/geography/postal-report rules before C1-3.
- Repository start commit: `44ff2b0351df2b08faa3bda92bb5b3d91ca720cc`.
- Commit: none created.

## 26. Active terminology correction - 2026-08-11 — HISTORICAL / SUPERSEDED

This checkpoint recorded the reversed Customer/marketer mapping. It is superseded by `CURRENT SNAPSHOT` and the foundation correction checkpoint; its old user-visible mapping must not be used.

### Result and evidence

- Active first-party UI labels changed without renaming models, fields, routes, API paths, template IDs, or JavaScript identifiers.
- Historical result was incorrect: this checkpoint inverted Customer and marketer labels. The active mapping is defined only by `CURRENT SNAPSHOT` and the later foundation correction checkpoint.
- Changed active shell, Customer/Lead/Interaction/Sale/report templates, `common/ui_views.py`, `common/static/common/kariz-app.js`, future maintained-page mapping, synthetic data, and matching tests.
- Generic metadata `سامانه مدیریت ارتباط با مشتری کاریز` remains because it names the CRM product class, not the Customer entity.
- Root `index.html` remains a read-only demo/reference. Its historical labels are outside the active Django UI.
- `python manage.py test --settings=config.test_settings -v 1` -> PASS; 283 run, 277 pass, 6 skip, 0 failure, 0 error.
- `python manage.py test common.tests.test_auth_shell_browser common.tests.test_sales_shell_browser --settings=config.test_settings -v 1` -> PASS; 4/4.
- Score 1: `8/10`; old browser readiness waits were intermittent. Fix: isolate cache/cookies/logs and wait for actual loaded profile values/page actions. Score 2: `9/10`.

## 27. Client-1 Lead Management decision gate - 2026-08-11

This section was created before any Lead Management expansion code. `BACKEND_SPEC.md` sections 5.3 and 15 identify every requested expansion contract as unresolved. Existing Lead behavior remains unchanged.

### Current approved carry-forward

- Keep scoped Lead create/list/retrieve/permitted edit, manual reassignment, append-only assignment history, current Customer/Product relations, follow-up fields, backend-owned status, direct-ID masking, safe reassignment audit, and no ordinary hard delete.
- Keep current role scope: Sales Agent sees assigned Leads plus own unassigned Leads and may edit only assigned Leads; Sales Manager, Company IT, and Platform Admin keep company-wide operational scope.
- Keep `status` server-owned and opaque. The database permits blank or historical text values; the API may filter exact values but cannot set or transition them.

### Decision: lead statuses

- State: `UNRESOLVED`.
- `new`, `assigned`, `contacted`, `no_answer`, `follow_up`, `not_interested`, `invalid_number`, `won`, and `lost` are provisional candidates only.
- Required approval: final codes and Persian labels; initial/terminal states; archive/conversion state versus separate event; blank/unknown history handling; `closed_at`; filters; migration mapping/refusal.
- No enum, constraint, default, rewrite, or transition endpoint may be added until approved.

### Decision: allowed transitions

- State: `UNRESOLVED`.
- Required approval: complete from-to matrix; actor roles and owner rule; required reason/evidence; reopen; concurrency/idempotency; timestamps; stage sync; audit.
- Current manual reassignment is the only approved Lead transition service. It does not change status.

### Decision: conversion rules

- State: `UNRESOLVED`.
- Required approval: trigger and roles; whether conversion creates Opportunity, Sale, both, or only changes state; cardinality; Customer/Product ownership; required fields; repeat/idempotency; atomic rollback; timestamps; undo; archive interaction; audit and visibility.
- Existing `mark_sale` must not be reinterpreted as conversion without approval.

### Decision: priority and archive

- Priority state: `UNRESOLVED`. Required: codes/scale, labels, default/null, change roles, ordering/tie-break, SLA/report meaning, audit, legacy migration.
- Archive state: `UNRESOLVED`. Required: flag/event versus status, archive/reopen roles and reason, list visibility, allowed later work, timestamps/history, retention/export.
- No priority/archive field, action, filter, sort, or control is approved.

### Decision: Opportunity and Pipeline

- State: `UNRESOLVED`.
- Opportunity needs approved purpose, Lead/Customer/Product cardinality, owner/team, fields, lifecycle, Sale/Lead win-loss relation, duplicates, archive, scope, and audit.
- Pipeline needs approved fixed/configurable model, stage codes/labels/order, transitions, entry/terminal stages, required data, forecast meaning, ownership, history, concurrency, API/UI/report contract.
- No Opportunity/Pipeline/Stage model, migration, endpoint, permission, template, or metric is approved.

### Result, blockers, and next action

- Requested expansion: `BLOCKED_DECISION`. Lead application code, migration, endpoint, template/style, permission, and architecture changed: none.
- Inspected: `BACKEND_SPEC.md`; Lead sections in handoff/roadmap; `sales/models.py`, `services.py`, `selectors.py`, `serializers.py`, `views.py`, `urls.py`; bounded workflow/scope tests; maintained Lead templates and active references.
- [lead statuses]: Final list and historical mapping absent. State machine cannot be built safely.
- [lead transitions]: From-to matrix and role rules absent. Authorization cannot be built safely.
- [conversion]: Target, cardinality, trigger, repeat rule, and rollback absent. Workflow cannot be built safely.
- [priority]: Values, default, owner, and ordering absent. Field meaning cannot be built safely.
- [archive]: Storage, reopen, visibility, and allowed work absent. Archive cannot be built safely.
- [opportunity pipeline]: Entity fields, owners, stages, transition rules, and Sale link absent. Schema cannot be built safely.
- Verification: full suite PASS 283 with 6 skips; system check PASS; migration drift PASS; API schema validation PASS with no warning; static dry-run, JavaScript syntax, HTML branding, and diff whitespace checks PASS.
- Self-correction score 1: `8/10`.
- [handoff order]: First insertion matched an older checkpoint and placed sections 26/27 before section 21. Chronology became wrong.
- Fix: moved both sections after section 25 and rechecked heading order.
- Self-correction score 2: `9/10`. Decision boundary, carry-forward behavior, blockers, exact approval inputs, roadmap state, and proof are consistent without invented code.
- Next phase after owner approval: data preflight/additive migration; models/constraints; transactional services/audit; selectors/permissions; serializers/actions/schema; Persian RTL UI; API/browser/concurrency/regression tests.
- Commit: none created.

## 28. Client-1 Interaction Management extension gate - 2026-08-11

### Confirmed scope and preserved behavior

- Target inclusion is confirmed for interaction timeline, follow-up tasks, meetings, calendar view, assigned responsible persons, and due dates.
- Telephony integration, call recording, and automatic reminders are explicitly excluded. They require separate approved services.
- Inclusion confirms product scope only. It does not define entity shape, lifecycle, authorization, calendar semantics, or acceptance behavior.
- Existing `Interaction` stays an append-only manual record bound to an authorized Lead and Customer.
- Server-owned `Interaction.agent` stays the recording actor, not an assumed responsible person. Optional `next_follow_up_at` stays follow-up information, not an assumed Task/Meeting/Reminder.
- Existing role/object scope, direct-ID masking, pagination/search/order, and immutable API stay unchanged.

### Decisions required before code

- Data shape: unified Activity versus separate FollowUpTask/Meeting; fields; relation to Interaction, Lead, and Customer.
- Timeline: event sources, immutable history, ordering/tie-break, pagination, edit/cancel representation.
- Task: title/details, statuses, create/complete/cancel/reopen, overdue, recurrence, completion evidence, correction.
- Meeting: start/end/due, timezone, location/channel, participants, statuses, reschedule/cancel/complete/no-show, outcome.
- Responsible person: eligible roles, default, assign/reassign authority, self-assignment, inactive user, Lead-assignee/recorder relation, history.
- Due date: date versus datetime, null rule, timezone and Jalali/Gregorian presentation, overdue boundary, edit/audit.
- Calendar: month/week/day, range bounds, event types, filters, overlap/all-day, Persian display.
- Authorization/audit: four-role object/write matrix, Lead-scope inheritance, no-hard-delete policy, archive/cancel, reasons, retention, concurrency/idempotency, safe audit.
- Acceptance: task, meeting, timeline-order, calendar, direct-ID, inactive-user, timezone-boundary, and concurrent-change examples.

### Result, blockers, and next action

- Status: `BLOCKED_DECISION`. Model, migration, API, UI, CSS, permission, scheduler, provider adapter, and architecture changed: none.
- Inspected: `BACKEND_SPEC.md`; handoff/roadmap contact sections; `sales/models.py`, `services.py`, `selectors.py`, `serializers.py`, `views.py`; current UI routes/views/templates and bounded test references.
- [task model]: Entity and lifecycle absent. Task cannot be built safely.
- [meeting model]: Time, participant, lifecycle, and reschedule rules absent. Meeting cannot be built safely.
- [timeline]: Event sources and deterministic order absent. Timeline cannot be built safely.
- [responsible person]: Eligibility, default, reassignment, and inactive-user rules absent. Assignment cannot be authorized safely.
- [due date]: Type, timezone, overdue, edit, and audit rules absent. Due behavior cannot be built safely.
- [calendar]: Timezone, Persian display, views, range, event types, and overlap absent. Calendar cannot be built safely.
- [excluded services]: Telephony, recording, and automatic reminders stay out. No media, worker, retry, provider, or scheduler work is allowed here.
- Verification: `python manage.py check --settings=config.test_settings` PASS; migration drift check PASS with no changes; extension-code absence guard PASS; handoff heading order PASS; `git diff --check` PASS.
- Self-correction score 1: `8/10`.
- [handoff order]: First append matched an older checkpoint and placed section 28 before section 21. Chronology was wrong.
- Fix: moved section 28 after section 27 and rechecked the full heading order.
- Self-correction score 2: `9/10`. Confirmed scope, exclusions, preserved behavior, decision gaps, proof, and exact unblock path are consistent without invented workflow code.
- Next action: owner approves the decisions above with one task, meeting, timeline-order, and calendar example. Then implement additive schema, services/audit, selectors/permissions, API/schema, Persian RTL UI, and tests.
- Commit: none created.

## 29. Client-1 Product Management Phase 1 - 2026-08-11

### Result and compatibility

- Phase status: `PARTIAL`; existing Product behavior remains compatible.
- Implemented exact Product active-state filtering on the existing list API and maintained Persian RTL list form.
- Accepted values are only `is_active=true` and `is_active=false`. Invalid values return HTTP 400. The parameter composes with existing search, ordering, and pagination.
- Backend role scope runs before the filter. Sales Agent still sees active Products only; asking for inactive Products returns an empty scoped list, not hidden rows. Elevated roles may filter active or inactive Products.
- Corrected create/edit SKU controls from `maxlength=64` to the model/API bound `maxlength=80`. Existing SKU, name, current price, description, role guards, deactivate action, and Sale price snapshots stay unchanged.
- No migration, new entity, new route, CSS change, layout change, inventory field, cost field, price variant, discount, or profit formula was added.

### Category and expanded-form decision boundary

- Category inclusion is confirmed for Product Phase 1, but its implementation contract is still `BLOCKED_DECISION`.
- Required Category decisions: flat versus hierarchy; name/code fields; uniqueness and case/Unicode handling; parent/order behavior; active/inactive lifecycle; moving a Product; behavior when a linked Category deactivates; deletion rule; role/audit scope; legacy Product migration; exact list/form/filter labels and acceptance examples.
- “Better product forms” confirms improvement scope but supplies no expanded field list. Current safe improvement is only validation-bound alignment. New catalog fields, required/null rules, choices, validation, ordering, and filters remain blocked until named.
- [product category]: Shape, uniqueness, lifecycle, and linked-Product behavior absent. Category schema cannot be built safely.
- [expanded product form]: Exact fields and validation absent. Form payload cannot be expanded safely.
- [product filtering]: Active-state filter is done. Category and any other new filter wait for their field contracts.

### FINAL_WAVE_LOW architecture boundary

- Inventory, stock, purchase cost, multi-price, discount, profit calculation, and their reports remain required `FINAL_WAVE_LOW`; none is delivered in Phase 1.
- Preparation is documentation-only. Current `Product` stays the catalog identity/current-sale-price boundary and is not polluted with guessed stock, warehouse, cost, discount, or profit columns.
- Future design must preserve immutable Sale product/price snapshots. Stock should use approved movement/concurrency rules; cost and price need approved snapshot/effective-time rules; discount needs stacking/authorization rules; profit needs an approved formula and return/cancellation treatment.
- No future model name, cardinality, formula, valuation method, endpoint, permission, or migration is approved by this boundary.

### Files, API, authorization, and tests

- Inspected: `BACKEND_SPEC.md`; Product/Inventory sections in handoff and root roadmap; `sales/models.py`, `services.py`, `selectors.py`, `serializers.py`, `views.py`; Product templates/client flow; bounded commercial/schema tests.
- Changed application files: `sales/views.py`, `common/templates/common/products/list.html`, `common/templates/common/products/detail.html`, `common/static/common/kariz-app.js`, `common/tests/test_commercial_shell.py`, `common/tests/test_system_api.py`, and `common/tests/test_sales_shell_browser.py`.
- Changed documentation: this handoff and the root Client-1 roadmap. Existing uncommitted section 28 changes were preserved.
- API change: existing `GET /api/v1/products/` adds optional exact `is_active` filter. No endpoint was added.
- Authorization: unchanged. Sales Agent remains read-only and active-only; Sales Manager, Company IT, and Platform Admin retain existing Product writes and inactive visibility.
- Focused proof: `python manage.py test common.tests.test_commercial_shell common.tests.test_system_api --settings=config.test_settings -v 1` PASS, 25/25.
- Static/system proof: JavaScript syntax PASS; Django check PASS; migration drift PASS with no changes.
- Full proof: `python manage.py test --settings=config.test_settings -v 1` PASS, 283 run with 6 skips, 0 failure, 0 error.
- Browser proof: first isolated attempt skipped because the local driver did not start; immediate verbose rerun PASS, 2/2, including the real inactive Product filter before the existing Product/Sale/report/audit flow.
- Remaining gates: OpenAPI validation PASS with no warning; collectstatic dry-run PASS; HTML branding PASS for 220 files; FINAL_WAVE_LOW code-absence guard PASS; heading order and `git diff --check` PASS.
- Self-correction score 1: `8/10`.
- [product filter browser]: API, template, and contract tests passed, but the first slice had no real browser action for the new select. UI proof was incomplete.
- Fix: added an inactive Product fixture and exercised `is_active=false` through the maintained filter form in the real browser test.
- Self-correction score 2: `9/10`. Scope-first filtering, strict validation, schema/UI/browser proof, form-bound correction, compatibility, and FINAL_WAVE_LOW isolation now meet the approved slice.
- Next action: approve the Category and expanded-field decisions above. Then implement Category in an additive migration/service/API/UI/test slice without touching FINAL_WAVE_LOW.
- Commit: none created.

## 30. Client-1 Sales expansion business-decision gate - 2026-08-11

This section is recorded before any Order, Quotation, Invoice, Payment, or Customer Account model. No schema work may start until the unresolved contracts below are approved.

### Confirmed business decisions

- Order, Quotation, Invoice, Payment, and Customer Account are separate domain modules. Existing `Sale` remains a separate operational success record and is not renamed or silently reused as any new module.
- Ordinary hard deletion is forbidden for all five modules and their historical child records. Cancellation, void, reversal, correction, archive, or another approved non-destructive transition must preserve history.
- Every financial mutation must create safe audit evidence. Audit must record actor, operation, object identity, approved state/value deltas, request trace, and time without secrets or private provider payloads.
- PDF export is deferred. No PDF route, artifact, layout, storage, signing, numbering, or download policy belongs to the first implementation slice.
- Tax behavior must be documented and explicitly approved before any taxable amount, tax field, tax-inclusive/exclusive calculation, rounding, invoice total, report, or fiscal behavior is implemented.
- Existing Sale quantity/unit-price/total snapshots and audited cancellation remain unchanged.

### Shared unresolved decisions

- Cross-module graph: allowed links and cardinality among Lead, Sale, Customer, Product, Quotation, Order, Invoice, Payment, and Customer Account.
- Conversion path: whether Quotation becomes Order, Order becomes Invoice, Sale creates any document, and whether one source may produce many targets; repeat/idempotency and rollback rules.
- Line items: required fields, Product optionality, description, quantity/unit, price source, immutable snapshots, line ordering, edits after issue, and partial fulfillment/invoicing.
- Money: currency, maximums, decimal scale, rounding point/mode, subtotal/total equations, tax-disabled behavior before tax approval, discount boundary, and negative/zero rules.
- Identity/numbering: human document numbers, uniqueness scope, generation time, gaps, concurrency, import, and correction/void references.
- Roles/scope: creator, issuer, approver, canceller, corrector, payer/cashier, account viewer, manager boundary, direct-ID masking, and field-level financial visibility.
- Time: draft/issue/due/payment/value/effective dates, timezone/calendar presentation, period boundaries, and backdating permissions.
- Lifecycle: final status codes and full transition matrix for every module; reason/evidence requirements; concurrency, idempotency, reversal, correction, reopen, and immutable states.
- Migration/import: legacy sources, opening balances, preflight, reconciliation totals, owner sign-off, rollback, and refusal on unknown data.
- Acceptance: redacted examples, expected totals, transition cases, permission attacks, concurrent writes, duplicate requests, audit rows, and cancellation/reversal outcomes.
- Delivery priority: the existing specification places full Quotation/Invoice/Payment/Customer Account work in `FINAL_WAVE_LOW`; this request does not explicitly approve a priority change. Exact scheduling remains unresolved.

### Tax precondition before Invoice or money implementation

- State: `BLOCKED_DECISION`; tax is not assumed to be zero, absent, included, or excluded.
- Required approval: jurisdiction and legal owner; seller registration/fiscal identity; taxable document types; taxable line/base; rate codes and effective dates; inclusive versus exclusive pricing; exemptions; per-line versus document calculation; discount-before/after-tax treatment; currency/decimal/rounding rule; immutable rate/base snapshots; correction/credit/void treatment; numbering/fiscal reporting fields; example input with expected line/subtotal/tax/grand-total values.
- Until approved, no `tax_*` field, rate table, default zero tax, subtotal/grand-total formula, invoice issuance calculation, tax report, or fiscal integration may be created.

### Module decision: Order

- State: `BLOCKED_DECISION`.
- Required: operational versus commercial meaning; Customer/Lead/Sale relation; line items; owner; status/transition table; approval; fulfillment; partial/cancel/correct; numbering; total source; whether it affects stock later.
- [order]: Entity fields, source, lifecycle, and downstream relations absent. Order model cannot be built safely.

### Module decision: Quotation

- State: `BLOCKED_DECISION`.
- Required: Customer/Lead relation; revision/version model; validity/expiry; line snapshots; accept/reject/withdraw; approval; numbering; conversion target; repeat conversion and stale-revision behavior.
- [quotation]: Revision, acceptance, expiry, and conversion rules absent. Quotation model cannot be built safely.

### Module decision: Invoice

- State: `BLOCKED_DECISION`.
- Required: internal versus legal/accounting meaning; source Order/Sale relation; line items; issue/void/correct; numbering; due date; amount equations; tax contract; fiscal fields only if approved; payment allocation; historical Customer/address/Product snapshots.
- [invoice]: Legal meaning, numbering, totals, tax, correction, and source relation absent. Invoice model cannot be built safely.

### Module decision: Payment

- State: `BLOCKED_DECISION`.
- Required: manual versus provider source; methods; currency/amount; payer/payee; Invoice allocation cardinality; partial/overpayment; pending/confirmed/failed/reversed/refunded states; idempotency; receipt/reference; reversal/refund and reconciliation.
- [payment]: Source, methods, allocation, states, idempotency, and reversal absent. Payment model cannot be built safely.

### Module decision: Customer Account

- State: `BLOCKED_DECISION`.
- Required: immutable ledger versus derived view; debit/credit convention; authoritative event sources; opening balance; currency; allocation; adjustment/reversal; outstanding/credit balance equation; close/reopen; statement date and visibility.
- [customer account]: Ledger authority, balance equation, event sources, and correction rules absent. Account model cannot be built safely.

### Implementation result and exact next action

- Application code, Django app/module, model, migration, API, UI route/template, navigation, permission, PDF, tax, payment provider, and architecture changed for this request: none.
- Inspected: `BACKEND_SPEC.md`; current Sale/Document/Finance decision sections; root roadmap C1-3 contract; current Sale model/services/selectors/serializers/views/UI/test references; audit boundary.
- The five roadmap checkpoints were updated after reviewing each requested module; every checkpoint remains fail-closed.
- Verification: Django system check PASS; migration drift PASS with no changes; requested-model absence guard PASS; handoff sections ordered 1 through 30; five roadmap module checkpoints present; `git diff --check` PASS.
- Self-correction score 1: `8/10`.
- [tax gate]: The first decision section stated tax approval was required but did not enumerate the minimum tax contract. Invoice work could still reopen from an ambiguous rule.
- Fix: added the explicit tax jurisdiction, base, rate, effective-date, inclusion, exemption, rounding, snapshot, correction, fiscal, and acceptance prerequisites above.
- Self-correction score 2: `9/10`. Separate-module intent, non-destructive lifecycle, financial audit, PDF deferral, tax gate, module blockers, roadmap checkpoints, and no-schema proof are now consistent.
- Next action: named sales, accounting, finance, security, and UAT owners approve the shared decisions and one redacted example per module. Tax decisions must be approved before Invoice money/schema work. Then implement one module at a time with a handoff/roadmap update after each module.
- Commit: none created.

## 31. Reporting expansion decision gate (2026-08-11)

### Requested scope and current result

- Requested dashboard: KPI cards, charts, and filters.
- Requested report families: sales, products, returns, delivery, profit/loss, and receivables.
- State: `BLOCKED_DECISION`.
- The request confirms target areas, but it does not define report formulas, source events, status inclusion, date bases, groupings, filter defaults, drill-down behavior, row/field scope, or acceptance examples. These rules must not be inferred from demo pages or labels.
- Existing `/api/v1/reports/user-performance/`, `/api/v1/exports/user-performance.xlsx`, and the maintained Persian user-performance page remain the only approved report contract. Their existing four metrics and authorization stay unchanged.
- No dashboard route, KPI card, chart, filter, report endpoint, export, model, migration, template, navigation activation, JavaScript, or CSS was added. Empty shells and dead controls were not added.

### Shared decisions required before any new report

- Metric names and exact formulas, including numerator, denominator, rounding, currency, quantity, sign, and zero/null behavior.
- Authoritative source entity and event for every measure; included/excluded lifecycle states; cancel, correction, return, and reversal treatment.
- Date field, timezone, Persian/Gregorian input contract, inclusive/exclusive boundaries, comparison period, and default range.
- Grouping dimensions, ordering, tie-breaks, totals/subtotals, pagination, maximum range, and query-growth bounds.
- Approved filters, defaults, multi-select behavior, unknown/out-of-scope identifier behavior, and filter combinations.
- Role, company, row, object, and field visibility for each report and drill-down.
- Dashboard freshness, cache policy if any, refresh trigger, chart series, axis, interval, empty/error/loading state, and card/chart click behavior.
- JSON, maintained UI, and XLSX parity where export is approved; PDF remains deferred.
- Redacted sample input and exact expected output for every metric and role.

### UI and API authorization contract

- UI and API must use the same authorized selector/service/report query object. UI filtering or hidden controls never widen or replace backend authorization.
- Current user-performance scope stays unchanged: Sales Agent sees self only; Sales Manager, Company IT, and Platform Admin see approved company/user rows.
- Every new report needs explicit row, object, aggregate, and sensitive-field scope. Until approved, its queryset is fail-closed and no UI route is exposed.
- The approval artifact must contain one matrix row for each fixed CRM role and report family. Each row must state allowed company/user/customer/product records, aggregate visibility, sensitive fields, permitted filters, drill-down targets, and export permission. An omitted cell means deny.
- Direct identifiers and drill-downs must be checked by the same backend scope as list/aggregate data; out-of-scope objects must not leak existence.
- API response, UI totals/cards/charts, and any approved export must derive from one scoped projection so counts and money cannot diverge.

### Dashboard decision

- State: `BLOCKED_DECISION`.
- Required: exact KPI cards and formulas; chart types and series; date/product/user/customer filters and defaults; comparison rules; refresh/freshness policy; drill-down targets; empty/error behavior; per-role visibility; sample expected dashboard for each role.
- [dashboard]: KPI and chart contracts absent. Live dashboard cannot show trusted data.

### Sales report decision

- State: `BLOCKED_DECISION`.
- Existing confirmed Sale data can be a candidate source only after approval.
- Required: count versus quantity versus amount measures; confirmed/cancelled treatment; `sold_at` versus creation date; grouping by user/product/customer/campaign; snapshot price use; currency/rounding; role and Customer/Product visibility; drill-down and expected examples.
- [sales report]: Measure, lifecycle, date, grouping, and scope rules absent. Sales totals may lie if guessed.

### Products report decision

- State: `BLOCKED_DECISION`.
- Existing Product and Sale data can support only an approved catalog or sales-performance projection; inventory must not be implied.
- Required: catalog versus performance purpose; active/inactive inclusion; sold quantity/revenue formulas; unsold-product treatment; current versus sale-snapshot price; category/grouping/order; date basis; scope and expected examples.
- [products report]: Report purpose and product measures absent. Product chart meaning stays unknown.

### Returns report decision

- State: `BLOCKED_DEPENDENCY_AND_DECISION`.
- No approved Return entity, return event, lifecycle, amount/quantity rule, or source relation exists.
- Required: return domain approval first, then statuses/transitions, original Sale relation, partial return, effective date, quantity/value sign, refund relation, cancellation/reversal, permissions, and expected examples.
- [returns report]: Return source data does not exist. Report cannot be computed.

### Delivery report decision

- State: `BLOCKED_DEPENDENCY_AND_DECISION`.
- No approved Delivery/Shipment entity, status history, carrier/tracking source, promised date, or delivered date exists.
- Required: delivery domain approval first, then lifecycle/history, source document, partial delivery, date/SLA rules, failure/cancel treatment, ownership/scope, and expected examples.
- [delivery report]: Delivery source and states do not exist. Report cannot be computed.

### Profit/loss report decision

- State: `FINAL_WAVE_LOW_BLOCKED_DEPENDENCY_AND_DECISION`.
- Purchase cost, inventory valuation, expenses, approved discounts/tax, return accounting, recognition basis, and currency rules do not exist as an approved contract.
- Required: accounting owner, cash/accrual basis, revenue recognition, COGS/cost method, expense sources, tax/discount/return treatment, period close/correction, currency/rounding, access scope, and exact examples.
- [profit/loss report]: Cost and accounting sources absent. Profit cannot be derived from sale price alone.

### Receivables report decision

- State: `FINAL_WAVE_LOW_BLOCKED_DEPENDENCY_AND_DECISION`.
- Invoice, Payment, Customer Account/ledger, due-date, allocation, and aging contracts remain blocked in section 30.
- Required: those approved modules first, then outstanding equation, as-of date, aging buckets, partial/overpayment and credit treatment, void/reversal/correction, customer statement scope, currency/rounding, and expected examples.
- [receivables report]: Ledger and allocation sources absent. Outstanding balance cannot be computed.

### Implementation result and exact next action

- Files inspected: `BACKEND_SPEC.md`; `KARIZ_PROJECT_HANDOFF.md`; root roadmap report and finance sections; `reports/services.py`; `reports/selectors.py`; `reports/serializers.py`; `reports/views.py`; current report URLs, maintained report template, sidebar report links, Sale/Product models, and report authorization/tests.
- Files changed: `KARIZ_PROJECT_HANDOFF.md` and the root roadmap only.
- Models/migrations/endpoints/templates/navigation/CSS changed: none.
- Blockers: approved metric contract, per-report scope, dashboard presentation contract, Return and Delivery domains, and financial source modules/rules.
- Verification: Django system check PASS; migration drift PASS with no changes; existing `reports` suite PASS (`16` tests); requested report source/entity guard PASS; handoff sections ordered `1` through `31`; seven roadmap checkpoints present; `git diff --check` PASS.
- Next phase: named business, sales, operations, accounting, security, and UAT owners approve the shared contract plus one redacted expected-output example per requested report and dashboard role. Then implement the smallest approved report end to end through one scoped projection, API, maintained UI, tests, and optional XLSX parity.
- Exact resume point: start with the first approved report whose source data already exists; sales or products is the likely technical candidate, but priority and rules remain an owner decision.
- Self-correction score 1: `8/10`.
- [report authorization]: Shared UI/API parity was recorded, but the required per-role approval artifact was not explicit. A later report could receive an ambiguous aggregate or drill-down scope.
- Fix: added a mandatory role-by-report matrix covering records, aggregates, sensitive fields, filters, drill-downs, and exports; omitted cells deny access.
- Self-correction score 2: `9/10`. Source dependencies, decision boundaries, fail-closed authorization, no-dead-UI behavior, roadmap state, and exact resume input are now explicit.
- Commit: none created.

## 32. Support modules pre-implementation policy gate (2026-08-11)

### Requested scope and gate result

- Requested modules: file management, folders, documents, tasks, and projects.
- The request confirms product inclusion. It does not supply the business lifecycle, ownership graph, storage backend, numeric limits, retention schedule, recovery targets, or role/object matrix needed for implementation.
- Operational file/document management remains `FINAL_WAVE_LOW` under `C1-CAP-FILE` and `C1-DEC-FILE-001`. The request does not explicitly approve a delivery-order change.
- Task/project work remains governed by `C1-DEC-CALENDAR-001` and section 28. Existing `Interaction.next_follow_up_at` is not silently converted into a Task or Project.
- Overall state: `BLOCKED_DECISION`; storage/scanner/backup destination and live recovery proof also `BLOCKED_EXTERNAL`.
- Application/Django app, model, migration, storage adapter, scanner adapter, endpoint, template, navigation, permission, task workflow, project workflow, CSS, and architecture changed: none.

### Storage policy security floor

The following floor is required before a file implementation may open:

- Binary objects are private by default and never served from the static tree or a public directory. Every read must pass backend object scope before an application download or approved short-lived object-storage response is produced.
- User input never selects a filesystem/object path. The server generates an opaque storage key; the original filename is bounded, sanitized display metadata only.
- Binary content is not stored in ordinary relational columns. The database stores bounded metadata and a storage reference; the selected private filesystem or object-storage backend remains an explicit deployment decision.
- An upload stays unavailable while type/signature validation and the approved malware scanner are pending. Extension-only trust is forbidden. Scanner failure is fail-closed.
- Exact allowed types, per-file size, per-owner/project/folder quota, storage backend/location, encryption/key custody, checksum algorithm, scanner/product, and upload timeout are unresolved and require named security/deployment-owner approval.
- Version, replace, archive, retention, legal hold, and purge behavior require an approved transition table. Until then, no replace or physical-delete/purge route is allowed.
- Metadata must not contain secrets or raw private content in logs. Audit records use bounded identifiers and operation facts only.
- [file storage]: Backend, limits, scanner, encryption custody, retention, and version rules absent. Binary upload cannot be enabled safely.

### Permission policy security floor

- Only active fixed-role CRM identities may enter the support-module API/UI. Django staff, superuser, group, direct-permission, or frontend visibility is not CRM authorization.
- List, retrieve, metadata read, content download, upload, create-folder, rename/move, version, archive, permission change, Task change, and Project change each require backend queryset/object authorization.
- Direct-ID access must use the same scope as list access and preserve the existing out-of-scope non-disclosure behavior. Download URLs or storage keys never bypass scope.
- Default is deny. Folder inheritance, Project membership, uploader ownership, Customer/Lead/Sale/Document links, manager scope, cross-project sharing, and Company IT/Platform Admin data scope may not be inferred.
- Approval must provide one matrix row per fixed role and action for File, Folder, Document, Task, and Project. Each row states allowed records, fields, links, create/change/archive/download/share actions, and audit visibility. An omitted cell means deny.
- Upload, download, version, move, archive, permission/share, Task assignment/status, and Project membership/status actions require bounded audit. File bytes, document body, secret link/token, and full original path are not audit payload.
- [support permissions]: Ownership, inheritance, sharing, and role/action matrix absent. Backend access cannot be opened safely.

### File backup and recovery rules

- The current guarded PostgreSQL backup covers database state only. It is not proof of backup for future file binaries.
- A file-capable release needs application-consistent recovery of database metadata and matching binary versions. Backup success requires an immutable manifest, object checksums, missing/orphan detection, and a restore/reconciliation result; copying only a volume or database is insufficient.
- Before release, owners must approve and prove one consistency protocol: bounded application write-stop, storage/database snapshot coordination, or a durable generation/cutoff marker. The contract must define uploads active at cutoff, staged/quarantined objects, completed versions, archive/purge tombstones, retries, and the point restored after partial failure. A database dump and an unrelated later blob copy do not form one backup.
- File backups must use an approved destination outside the live application/storage failure domain, an approved off-host copy, protected encryption keys, bounded operator access, monitored schedule, overlap/timeout behavior, and failure/missed-run alerts.
- Retention must preserve version history and legal holds. Automated deletion is forbidden until exact daily/weekly retention, purge scope, hold precedence, and rollback behavior are approved and tested.
- Restore must target a new isolated disposable database and private disposable file store. It must not overwrite live metadata or blobs. Recovery proof must validate checksums, metadata-to-object links, denied public access, and a sample authorized download without exposing private content.
- Exact destination, schedule, retention, backup owner, restore owner, RPO, RTO, key recovery, off-host rule, maximum dataset, and acceptance evidence remain `BLOCKED_EXTERNAL` under `C1-DEC-RUNTIME-001`.
- [file backup]: Current runbook has no binary-store contract. A future file module would have incomplete recovery.

### File management, Folder, and Document decisions still required

- File management: metadata fields, uploader/source, accepted content classes, checksum/deduplication meaning, quarantine states, version relation, entity links, archive/hold/purge, and error/idempotency rules.
- Folder: personal/shared/entity root meaning; parent cardinality; unique-name scope; maximum depth; cycle guard; create/rename/move/archive; child behavior; permission inheritance/override; ordering and concurrent move rules.
- Document: business document versus uploaded binary meaning; whether one Document has many File versions; title/type/number fields; Customer/Lead/Sale/Project links; draft/final/archive lifecycle; immutable versions; correction; retention/hold; download disposition.
- Storage migration: local-to-object or provider-to-provider copy, checksum proof, dual-read/write policy, rollback, orphan handling, and maintenance window.
- Acceptance: safe sample files plus oversize, empty, malformed, type-spoof, malware, path, Unicode filename, duplicate, concurrent version, direct-ID leak, expired download, retention/hold, backup, and restore cases.
- [folder]: Root, hierarchy, move, cycle, naming, and inheritance rules absent. Folder model cannot be built safely.
- [document]: Business meaning, links, fields, lifecycle, and File-version relation absent. Document model cannot be built safely.

### Task and Project decisions still required

- Task: exact fields, relation to Project/Customer/Lead/Interaction, creator/owner/assignee, statuses and transitions, priority, due date/timezone, completion/cancel/reopen, overdue, archive, recurrence boundary, inactive assignee, correction, concurrency, and audit.
- Project: purpose, fields, owner, members/roles, Customer or commercial links, statuses/transitions, date bounds, Task cardinality, move/remove behavior, archive/reopen, visibility, inactive member handling, and audit.
- Cross-module links: whether files/folders/documents attach to Project, Task, or both; attachment ownership after move/archive; permission intersection; retention after parent archive; and direct-ID behavior.
- Automatic reminders remain excluded unless separately approved. No scheduler, notification provider, or recurrence engine is implied by Task due dates.
- Acceptance: one redacted Project with members, Tasks, state changes, due-date boundaries, inactive assignee, attachment links, direct-ID isolation, concurrent updates, archive/reopen, and exact expected audit.
- [task]: Fields, lifecycle, time, assignment, and Project relation absent. Task model cannot be built safely.
- [project]: Purpose, membership, lifecycle, scope, and Task relation absent. Project model cannot be built safely.

### Implementation order after approval

1. Approve `C1-DEC-FILE-001`, `C1-DEC-CALENDAR-001`, the role/action matrix, and the live storage/backup inputs with redacted acceptance examples.
2. Add only the approved metadata entities and additive migrations; update entity/relationship/API documents separately.
3. Add transactional lifecycle services and bounded audit before write endpoints.
4. Add scoped selectors/permissions and direct-ID isolation tests before UI or download access.
5. Add the private storage/scanner adapter and file backup/isolated restore proof before enabling binary upload in a release.
6. Add versioned API, maintained Persian RTL UI, and browser tests without using template-only demo pages as implementation evidence.

### Inspection, blockers, and exact resume point

- Files inspected: `BACKEND_SPEC.md`; `KARIZ_PROJECT_HANDOFF.md`; root roadmap support/runtime sections; `config/settings.py`; `accounts/models.py`; `accounts/access.py`; `common/permissions.py`; `auditlog/services.py`; active model/config/sidebar/test references; `compose.yml`; `.env.example`; `docs/ops/BACKUP_RESTORE.md`.
- Existing code finding: no File, Folder, Document, Task, or Project model; no `FileField`/`ImageField`; no `MEDIA_ROOT`, `MEDIA_URL`, application storage backend, binary upload parser, file-serving route, or binary-store backup contract. Current sidebar entries are disabled future placeholders.
- Files changed for this request: `KARIZ_PROJECT_HANDOFF.md` and the root roadmap only.
- Blockers: storage backend and numeric limits; scanner; retention/hold/version rules; five-module entity/lifecycle graph; role/action matrix; live destination/schedule/off-host/RPO/RTO/owners; safe samples and expected outcomes.
- Exact next action: named business, records/data, security, deployment/backup, and UAT owners approve the two decision records and supply one redacted folder/document/file case plus one Project/Task case. Then start with metadata/schema only; keep binary upload closed until scanner and recovery proof pass.
- Verification: Django system check PASS; migration drift PASS with no changes; focused permission/production-backup suite PASS (`61` tests); support model/storage-setting absence guard PASS; handoff sections ordered `1` through `32`; six roadmap module checkpoints present; `git diff --check` PASS.
- Self-correction score 1: `8/10`.
- [backup consistency]: Manifest and checksum rules existed, but no database/blob cutoff or in-flight upload rule was explicit. A restore could pair metadata with the wrong binary generation.
- Fix: added a mandatory approved consistency protocol covering write-stop/snapshot/generation cutoff, active and quarantined uploads, completed versions, tombstones, retry, and partial failure.
- Self-correction score 2: `9/10`. The security floor, unresolved business values, authorization matrix, recovery consistency, module blockers, proof, and exact resume path are now explicit without unsafe implementation.
- Commit: none created.

## 33. Client-1 foundation correction — completed 2026-08-12

### Result and current role truth

- Local state: `DONE`; no external release/runtime claim is added.
- Customer means the actual store/customer/client contact. Active Persian labels are `مشتری` / `مشتریان`. The `Customer` model, API path, database table, fields, and stable identifiers remain unchanged.
- `sales_agent` = `بازاریاب (کال سنتر)`; this is a User, never a Customer.
- `sales_manager` = `مدیر فروشگاه`.
- `company_it` = `مدیر فنی مشتری`; it cannot grant, target, see, or manage Platform Admin through user administration.
- `platform_admin` = `مدیر پلتفرم`; it retains highest CRM application custody.
- Existing backend queryset/object authorization remains authoritative. No permission behavior was weakened or moved to frontend-only hiding.

### Files inspected

- Authority/status: `BACKEND_SPEC.md`; `KARIZ_PROJECT_HANDOFF.md`; root roadmap; `AGENTS.md`.
- Backend/API: `config/urls.py`; `accounts/urls.py`; `accounts/views.py`; `accounts/serializers.py`; `accounts/models.py`; `accounts/access.py`; `accounts/management/commands/seed_synthetic_uat.py`; `sales/urls.py`; `sales/views.py`; `sales/serializers.py`; `sales/selectors.py`; `reports/urls.py`; `reports/views.py`; `reports/serializers.py`; `reports/selectors.py`; `auditlog/urls.py`; `auditlog/views.py`; `auditlog/serializers.py`; `auditlog/selectors.py`; relevant account, customer, sale, report, audit, and synthetic-UAT tests.
- Active frontend: `common/templates/common/base.html`; `home.html`; `login.html`; all maintained `users/`, `customers/`, `leads/`, `interactions/`, `products/`, `sales/`, `reports/`, and `activity_logs/` templates; `common/static/common/kariz-app.js`; `common/static/common/kariz.css`; `common/ui_views.py`; `common/ui_urls.py`; `common/tests/test_auth_shell.py`; `common/tests/test_auth_shell_browser.py`; `common/tests/test_sales_shell.py`; `common/tests/test_sales_shell_browser.py`; `common/tests/test_commercial_shell.py`.
- Exact curated visual references inspected: `authentication/layouts/corporate/sign-in.html`; `index.html`; `dashboards/store-analytics.html`; `dashboards/call-center.html`; `dashboards/finance-performance.html`; `apps/user-management/users/list.html`; `apps/user-management/users/view.html`; `apps/customers/list.html`; `apps/customers/view.html`; `apps/contacts/getting-started.html`; `apps/contacts/add-contact.html`; `apps/contacts/edit-contact.html`; `apps/contacts/view-contact.html`; `apps/ecommerce/catalog/products.html`; `apps/ecommerce/catalog/add-product.html`; `apps/ecommerce/catalog/edit-product.html`; `apps/ecommerce/sales/listing.html`; `apps/ecommerce/sales/details.html`; `apps/ecommerce/sales/add-order.html`; `apps/ecommerce/reports/sales.html`; `apps/ecommerce/reports/view.html`.
- Reference finding: no exact curated Lead, Interaction, or Audit page exists. Contact pages are visual analogues only. Demo content supplied no business rule.

### Files changed

- Policy/contracts/status: `AGENTS.md`; `BACKEND_SPEC.md`; `KARIZ_PROJECT_HANDOFF.md`; root roadmap; new `docs/frontend/FRONTEND_REFERENCE_MAP.md`.
- Active UI: `common/ui_views.py`; `common/static/common/kariz-app.js`; `common/templates/common/base.html`; Customer, Lead, Interaction, Sale, Report, and User list/detail templates.
- Data/guards/tests: `accounts/management/commands/seed_synthetic_uat.py`; `accounts/tests/test_seed_synthetic_uat.py`; `scripts/check_html_branding.py`; `common/tests/test_auth_shell.py`; `common/tests/test_auth_shell_browser.py`; `common/tests/test_commercial_shell.py`; `common/tests/test_sales_shell.py`; `common/tests/test_sales_shell_browser.py`.
- Unchanged by design: models, migrations, API paths, database identifiers, CSS, architecture, and permissions. No Lead pipeline, Task, Invoice, SMS, finance, inventory, file, or other business model was added.

### Terminology and frontend-reference result

- Sidebar, Customer create/list/detail/edit/deactivate, Lead, Interaction, Sale, report, user-role UI, UI errors, client messages, synthetic UAT data, and active UI/browser tests now use the authoritative terms.
- Customer screens no longer render `بازاریاب (کال سنتر)`. Lead reassignment uses that label only for the responsible User.
- `docs/frontend/FRONTEND_REFERENCE_MAP.md` maps every maintained page to business screen, template, JavaScript handler, real endpoint, allowed role/scope, exact reference, and major UX gap.
- The frontend read policy now has a narrow exact-file reference allowlist. Dependency, plugin, media, font, minified, generated, build, vendor-internal, and secret trees remain excluded.

### Verification evidence

- `python manage.py check --settings=config.test_settings`: PASS.
- `python manage.py makemigrations --check --dry-run --settings=config.test_settings`: PASS; no migration drift.
- Focused auth/browser shell: PASS, `17/17`.
- Full Django suite: PASS, `284/284`; `6` intentional skips.
- OpenAPI validation: PASS.
- `node --check common/static/common/kariz-app.js`: PASS.
- Active browser suites: PASS, `4/4`.
- `python scripts/check_html_branding.py`: PASS, `220` files.
- Collectstatic dry-run: PASS, `179` files.
- Active `مخاطب` / `مخاطبین` guard: PASS; only the negative regression assertion contains those words.
- Customer-as-marketer regression guard: PASS.
- `git diff --check`: PASS after final documentation update.

### Self-correction and resume point

- Score 1: `8/10`.
- [role shell test]: Source mapping and one browser role were covered, but all four rendered role labels lacked one direct shell regression test. A future label drift could escape.
- Fix: added one server-rendered shell test covering all four fixed roles; focused and full suites pass.
- Score 2: `9/10`.
- Remaining decision blockers: `C1-DEC-GOV-001`, `C1-DEC-SEAT-001`, `C1-DEC-TEAM-001`, and `C1-DEC-AFTER-001`; `23` consolidated IDs remain wholly open.
- Exact next phase: approve GOV/SEAT/TEAM/AFTER, then run C1-2 with backend authorization, maintained Persian RTL UI, API tests, and browser tests in the same slice.
- Git HEAD: `fa32e5287e8caa10eba688f2d84efe23a6cc9947`.
- Git status: dirty; exact changed paths are the files listed in this checkpoint plus untracked `docs/frontend/FRONTEND_REFERENCE_MAP.md`. No commit created.
