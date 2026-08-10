# Kariz CRM project handoff

این فایل تنها منبع زنده وضعیت، پیشرفت، blocker، شاهد، تصمیم باز و اقدام دقیق بعدی پروژه است. `BACKEND_SPEC.md` قرارداد پیاده‌سازی است؛ اسناد `docs/backend/` قراردادهای فنی و اسناد `docs/ops/` runbookهای عملیاتی هستند و هیچ‌کدام جایگزین وضعیت زنده این فایل نیستند.

## 1. مرز وضعیت و تحویل

| جریان | وضعیت زنده | معنی |
|---|---|---|
| **CURRENT CORE RELEASE** | `production candidate; external verification pending` | هسته repository تست شده است؛ PostgreSQL زنده، Docker، Nginx، TLS، مرورگر، backup/restore، load و زیرساخت مقصد هنوز proof بیرونی می‌خواهند. |
| **FULL 74-CAPABILITY PRODUCT** | `work in progress` | 74 ردیف ممیزی دارد: 46 ردیف دارای پوشش backend و 28 ردیف دارای HTML shell؛ هیچ‌کدام بدون `VERIFIED_END_TO_END` به معنی تحویل کاربر نهایی نیست. |
| **DELIVERY TARGET** | `scoped Kariz CRM V1 only` | فقط V1 تاییدشده در `BACKEND_SPEC.md` مجاز است. دامنه‌های آینده بدون تصمیم مکتوب و تغییر scope ساخته یا تحویل‌شده اعلام نمی‌شوند. |

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

## 3. قابلیت‌های داخل V1

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

## 4. قابلیت‌های صریحا خارج از DELIVERY TARGET

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

## 6. فازهای DELIVERY TARGET V1

- [x] **V0 — Backend core:** schema، service، API، authorization، audit، report/XLSX و repository tests ساخته شد.
- [x] **V1 — Truth consolidation:** status/spec/roadmap/blocker truth در همین handoff ادغام شد؛ دو سند موقت حذف و disclaimer قابلیت اصلاح شد.
- [ ] **V2 — Connected application shell:** routeهای تاییدشده، API client same-origin/CSRF، navigation فارسی/RTL، brand cleanup و stateهای خطا/خالی ساخته شود.
  - [x] **V2-A — HTML branding guard:** همه 202 فایل HTML/template first-party، شامل archive، پاک‌سازی و با scan خودکار guard شدند.
  - [ ] **V2-B — Connected auth shell:** sign-in/logout/me واقعی و stateهای Session/CSRF به رابط منتخب وصل شود.
- [ ] **V3 — Core browser flows:** auth/user/customer/phone/Lead/Interaction/Product/Sale/report/audit به backend واقعی وصل و role/browser tests پاس شود.
- [ ] **V4 — Safe low-ambiguity completion:** filterهای دقیق، customer overview، assignment history read API، audit summary و bounded bulk deactivate فقط در صورت انطباق با spec اجرا شود.
- [ ] **V5 — External core proof:** PostgreSQL، Compose، Nginx، TLS، static، health، write-stop، browser، backup/restore، load و scan روی release دقیق پاس شود.
- [ ] **V6 — Scoped V1 UAT/cutover:** profile تحویل، migration/reconciliation در صورت نیاز، UAT، training، rollback و owner sign-off پاس شود.

## 7. رجیستر FULL 74-CAPABILITY PRODUCT — خارج از مجوز تحویل فعلی

این رجیستر فقط هدف و dependency order محصول کامل را حفظ می‌کند. هیچ phase آینده بدون scope و تصمیم مکتوب شروع نمی‌شود.

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
- [x] full local suite: 232 pass؛ 6 PostgreSQL-only روی SQLite عمدا skip.
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
- UI فعال فعلی: `/` و Django admin.
- health: `/api/v1/health/live/` و `/api/v1/health/ready/`.
- migration heads: `accounts.0002_user_role_constraint`، `auditlog.0002_activitylog_role_snapshots` و `sales.0010_interaction_contract`.
- routeهای اصلی: auth login/logout/me، users/change-role، customers، customer-phones، leads/reassign، interactions، products، sales/cancel، activity-logs، user-performance JSON و XLSX.
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

## 15. اقدام دقیق بعدی

**V2-B، connected auth shell:** فقط فایل‌های allowlisted صفحه sign-in، home shell، auth API contract و testهای مرتبط بررسی شوند؛ login واقعی با `username`/`password`، Session + CSRF، logout و `me` به routeهای Django وصل شود؛ حالت‌های inactive، throttle، validation، 403/404 امن، متن فارسی/RTL و browser smoke اضافه شود؛ سپس evidence و capability state همین فایل به‌روز شود.

در این checkpoint کار متوقف می‌شود. توسعه V2 در این مرحله شروع نمی‌شود.
