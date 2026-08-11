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
- authorization: backend تغییر نکرد؛ UI همان active CRM identity و admin role boundary را پیش از render اعمال می‌کند. Company IT مدیر سامانه را نمی‌بیند و نمی‌تواند role بالاتر از خود بدهد.

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

## 18. اقدام دقیق بعدی

**V4، safe frontend cleanup و Persian/branding:** فقط active reachable first-party HTML را batch کوچک بررسی کن؛ candidate manifest و reference proof بساز؛ dead demo/vendor-visible link و unused non-Persian active locale را با safe deletion policy پاک کن؛ بعد template/static/browser gates و handoff evidence را اجرا کن.

در این checkpoint کار متوقف می‌شود.

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
