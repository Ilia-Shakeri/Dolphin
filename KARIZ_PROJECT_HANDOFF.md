# Kariz CRM project handoff

این فایل تنها منبع زنده وضعیت، پیشرفت، blocker، شاهد و تصمیم باز پروژه است. `BACKEND_SPEC.md` قرارداد normative پیاده‌سازی است؛ `docs/backend/*.md` قراردادهای فنی جزئی، `docs/ops/*.md` runbookهای عملیاتی، و `KARIZ_CLIENT1_CODEX_ROADMAP.md` نقشه فازبندی‌شده است. هیچ‌کدام جایگزین وضعیت زنده همین فایل نیستند. سوابق checkpoint قدیمی‌تر از این بازنویسی (P0 — ۲۰۲۶/۰۸/۱۴) در `git log` و در تاریخچه همین فایل قابل بازیابی است؛ اینجا فقط نتیجه نهایی و شواهد فعلی نگه داشته می‌شود.

## ۱. عکس فوری وضعیت فعلی — ۲۰۲۶/۰۸/۱۴ — ممیزی P0

- ریشه مخزن: `C:\Users\Dear-OTCamp-User\Desktop\Kariz-CRM`. شاخه: `main`. HEAD واقعی: `58b25a18cf8fe538710ac03521b256ca18fe3f81` («feat: enhance synthetic UAT data generation with after-sales support and browser testing»).
- `git status --short` قبل از این ممیزی فقط یک خط داشت: `D AGENTS.md` — حذف تغییرنیافته و pre-existing از قبل این نشست؛ جزو کار P0 نیست و در commit مستندسازی این فاز stage نشد.
- عکس فوری قبلی این فایل (مربوط به HEAD `d491f1d...`) و ادعای «۶ مسیر porcelain باقیمانده» اکنون منسوخ است: commit بعدی (`58b25a1`) همان تغییرات را ثبت کرد و درخت کاری اکنون تمیز است (به‌جز `AGENTS.md`). این خودش نمونه دقیق «prose قدیمی در برابر شاهد اجراشده» است که این ممیزی موظف به اصلاح آن بود.
- `docs/ops/SOURCE_MANIFEST.md` و `docs/ops/RELEASE_NOTES.md` یک reference منجمد و تاریخی روی commitهای بسیار قدیمی‌تر (`50a978a`، `95dbc71e`) دارند؛ هر دو commit در تاریخچه واقعی مخزن موجودند ولی به‌شدت عقب‌تر از HEAD فعلی هستند. آن دو سند صریحا خود را «historical, not live status» اعلام می‌کنند؛ به‌عنوان شاهد وضعیت فعلی استفاده نشوند. از زمان آن reference هیچ immutable release reference تازه‌ای تولید نشده است.

## ۲. تصمیم‌های مستقیم کاربر که اکنون معتبرند

این‌ها تصمیم مالک محصول برای برنامه‌ریزی هستند و بر prose قدیمی هر سند دیگر اولویت دارند:

- محصول Kariz CRM / کاریز؛ رابط کاربر نهایی نگهداری‌شده فارسی-only، RTL، responsive و same-origin است. Monolith ماژولار می‌ماند مگر کد موجود خلاف آن را ثابت کند (کد فعلی این‌طور است: یک Django project با appهای `accounts/sales/aftersales/communications/auditlog/reports/common`، بدون microservice).
- یک کدبیس مشترک برای چند استقرار مشتری؛ فورک یا شاخه دائمی مشتری‌محور ممنوع؛ هر استقرار DB/secret/runtime identity/backup/branding/feature-profile جدا دارد؛ `if client_name == ...` در کد پخش نشود؛ فعال/غیرفعال بودن feature از role permission و object scope جدا است؛ غیرفعال‌کردن feature داده تاریخی را پاک نمی‌کند؛ profile یا dependency ناشناخته fail-closed است. **وضعیت فعلی کد: هیچ مدل/مکانیزم DeploymentProfile یا FeatureFlag در کد وجود ندارد (تایید شد — هیچ چنین کلاسی در هیچ app پیدا نشد). این یک اصل تاییدشده برای طراحی آینده است، نه یک قابلیت پیاده‌سازی‌شده.** به بخش ۷.
- نقش‌های ثابت Client 1 (کد فعلی دقیقا همین چهار نقش را دارد؛ تایید شد در `accounts/models.py`): `platform_admin` (فقط تیم مالک/توسعه)، `sales_manager` (مدیر فروشگاه مشتری)، `sales_agent` (بازاریاب/فروشنده، حساب کاربری جدا برای هرکس، بدون حساب اشتراکی)، `company_it` (برای Client 1 غیرفعال یا حداکثر یک حساب فنی محدود بعدی). `platform_admin` تنها نقش مجاز به ساخت/غیرفعال‌سازی کاربر، تغییر نقش و reset رمز است؛ `sales_manager` مدیریت کاربر ندارد مگر تصمیم مستقیم بعدی. احراز هویت فعلی نام‌کاربری/رمز است؛ دسترسی فقط از سیستم‌های کنترل‌شده شرکت در دفتر تهران روی مسیر شبکه خصوصی درنظر گرفته می‌شود. Django Admin نباید به کاربر عادی یا شبکه عمومی افشا شود.
- هدف کامل محصول Client 1 (بخش ۴) شامل موجودی/مالی/حسابداری هم می‌شود؛ جمله قدیمی «Inventory و مالی همیشه خارج از هدف Client-1 هستند» دیگر معتبر نیست، ولی این ماژول‌ها تا عبور از gate خودشان `ABSENT`/`BLOCKED_DECISION` علامت می‌مانند.
- محدودیت‌های deployment گزارش‌شده توسط مشتری (بخش ۱۰) ورودی بیرونی تاییدنشده هستند، نه fact اثبات‌شده؛ تا شواهد `winver`/`systeminfo` واقعی، Windows Server 2008 هدف تولید تلقی نمی‌شود.
- مدل تهدید حفاظت سورس (بخش ۸): مالک فیزیکی هاست دسترسی Administrator دارد؛ رازداری مطلق سورس از مالک فیزیکی خصمانه فنی تضمین‌شدنی نیست؛ هدف واقعی نبود repo/toolchain/تست/مستندات توسعه در محیط تحویل و کنترل توزیع/rollback فقط توسط مالک پلتفرم است.
- برندینگ: برند فعال فقط `Kariz CRM`/`کاریز`؛ هیچ نام مشتری در سورس مشترک hardcode نشود؛ شناسه‌های runtime پایدار مثل `KTMenu`/`data-kt-*` کورکورانه rename نشوند؛ notice/license شخص‌ثالث حذف نشود.

## ۳. پایه فعلی پیاده‌سازی‌شده (baseline تایید شده با کد واقعی)

تایید مستقل با خواندن `models.py`، لیست migrationها، `urls.py`، `selectors.py`، `services.py` هر اپ (نه فقط prose سند):

- احراز هویت/نشست/پروفایل با Session+CSRF same-origin؛ چهار نقش ثابت با enforcement واقعی در `accounts/access.py` (فیلتر `Exists` روی staff/superuser/group/direct-permission، نه فقط ادعای مستند).
- User با مدیریت کنترل‌شده (بدون DELETE)، workstream محدود `sales`/`after_sales`، نگهبان آخرین Platform Admin فعال.
- Customer، CustomerPhone (نرمال‌سازی ایرانی، شماره اصلی یگانه، جلوگیری duplicate فعال)، Lead، LeadAssignmentHistory، Interaction (append-only).
- ProductCategory (flat، migration `sales.0013`) و Product (با brand/barcode اختیاری).
- Sale تاییدشده/لغوشده با snapshot قیمت؛ SalesDocument و PostalStatusHistory داخلی (سند حسابداری/حقوقی نیست).
- AfterSalesRequest و AfterSalesHistory (`aftersales` app، migration `0001`) با workstream ایزوله.
- InboundSMS (`communications` app، migration `0001`): ذخیره و گزارش provider-neutral داخلی؛ **بدون آداپتور زنده** — `communications/adapters.py` فقط یک `Protocol` تعریف می‌کند، هیچ کلاس concrete آن را پیاده نکرده، هیچ فراخوانی HTTP خروجی به provider در کد نیست (grep برای `requests|httpx|urllib.request` صفر نتیجه داد)، و هیچ route وبهوک عمومی/authenticated ثبت نشده — فقط سه GET report/drilldown/detail.
- ActivityLog (`auditlog` app) با role/account-object snapshot و audit امن.
- گزارش عملکرد کاربر (چهار متریک: `customers_created_count`، `sales_count`، `sales_amount`، `average_sale_amount`) با parity کامل JSON/UI/XLSX، به‌علاوه گزارش سند/پستی و گزارش پیامک ورودی.
- API نسخه‌دار `/api/v1/`، OpenAPI معتبر، health live/ready، error envelope پایدار.
- **تایید غیاب صریح:** grep برای `class\s+(Invoice|InvoiceItem|Payment|Order|Quotation|Inventory|Stock|Warehouse|Cheque|Installment|CustomerAccount|Ledger|Task|Project)` و `FileField|ImageField` و `pdf|reportlab|weasyprint` در کل appهای first-party صفر نتیجه داد. این ماژول‌ها و ذخیره فایل/PDF در کد وجود ندارند — نه partial، نه HTML shell به‌تنهایی بدون backend.

## ۴. هدف کامل موردنیاز Client 1

فهرست کامل خواسته‌شده در پرامپت مالک محصول (احراز هویت…backup/restore…یکپارچگی بیرونی) به بخش ۵ (ماتریس قابلیت) نگاشت شده است. هیچ ماژول جدید فقط به‌خاطر «هدف است» implemented اعلام نمی‌شود؛ هرکدام باید gate تصمیم و acceptance مخصوص خودش را در `KARIZ_CLIENT1_CODEX_ROADMAP.md` بگذراند. یکپارچگی‌های بیرونی (وب‌سایت، درگاه پرداخت، حسابداری، پیامک، ایمیل، تلفنی) تا مستندات رسمی provider + credential + owner برسد `BLOCKED_EXTERNAL` می‌مانند.

## ۵. ماتریس قابلیت فعلی

وضعیت‌ها: `IMPLEMENTED_LOCAL` (backend محلی کامل، UI متصل claim نمی‌شود)، `UI_CONNECTED_LOCAL` (backend+UI واقعی محلی متصل و تست‌شده؛ بدون proof محیط هدف)، `HTML_SHELL_ONLY`، `ABSENT`، `BLOCKED_DECISION`، `BLOCKED_EXTERNAL`، `RUNTIME_UNPROVED`، `VERIFIED_END_TO_END` (فقط با proof رانتایم/UAT واقعی هدف). هیچ ردیفی زیر بدون شواهد رانتایم دقیق هدف `VERIFIED_END_TO_END` نیست.

| قابلیت | Backend (model/migration/service/API) | UI محلی | وضعیت | blocker دقیق |
|---|---|---|---|---|
| ورود/نشست/پروفایل | کامل | متصل، تست‌شده | `UI_CONNECTED_LOCAL` | proof مرورگر/TLS روی هاست هدف |
| کاربران و نقش ثابت | کامل، بدون DELETE | متصل | `UI_CONNECTED_LOCAL` | — |
| Customer/Phone | کامل | متصل | `UI_CONNECTED_LOCAL` | — |
| Lead/Assignment/Interaction | کامل؛ روش تخصیص اولیه هنوز باز | متصل | `UI_CONNECTED_LOCAL` | BIZ-001 تخصیص اولیه |
| ProductCategory/Product | کامل (`sales.0013`) | متصل | `UI_CONNECTED_LOCAL` | — |
| Sale | کامل (تایید/لغو) | متصل | `UI_CONNECTED_LOCAL` | BIZ-006 correction semantics |
| SalesDocument/Postal | کامل، فقط عملیاتی (نه سند حسابداری) | متصل | `UI_CONNECTED_LOCAL` | واژگان وضعیت پستی دقیق تایید نشده |
| After-Sales | کامل، workstream ایزوله، close نهایی | متصل | `UI_CONNECTED_LOCAL` | گراف status/reopen/SLA تایید نشده |
| InboundSMS ذخیره/گزارش داخلی | کامل، provider-neutral | متصل | `UI_CONNECTED_LOCAL` | — |
| اتصال زنده provider پیامک | Protocol فقط | ندارد | `BLOCKED_EXTERNAL` | مستندات/credential رسمی provider (`docs/backend/SMS_PROVIDER_ADAPTER_REQUIREMENTS.md`) |
| گزارش عملکرد کاربر + داشبورد | کامل، چهار متریک | متصل، چارت/drill-down واقعی | `UI_CONNECTED_LOCAL` | فرمول‌های جدید نیازمند تصویب |
| ActivityLog/Audit | کامل، Company IT محدود | متصل | `UI_CONNECTED_LOCAL` | BIZ-011 محدوده audit مدیر فروشگاه |
| Inventory/Stock movement | ندارد | ندارد | `ABSENT` | قرارداد واحد/انبار/رزرو/منفی‌شدن تایید نشده |
| Order | ندارد | ندارد | `ABSENT` | BLOCKED_DECISION کامل |
| Quotation | ندارد | ندارد | `ABSENT` | BLOCKED_DECISION کامل |
| Invoice/InvoiceItem (حسابداری/حقوقی) | ندارد | ندارد | `ABSENT` | مالیات، شماره‌گذاری، اصلاح، snapshot تایید نشده |
| Payment | ندارد | ندارد | `ABSENT` | روش/تخصیص/idempotency تایید نشده |
| چک/قسط | ندارد | ندارد | `ABSENT` | BLOCKED_DECISION کامل |
| Customer Ledger/حساب مشتری | ندارد | ندارد | `ABSENT` | قرارداد بدهکار/بستانکار تایید نشده |
| مطالبات (Receivables) | ندارد | ندارد | `ABSENT` | وابسته به Invoice/Payment |
| سود/زیان | ندارد | ندارد | `ABSENT` | وابسته به Inventory/هزینه |
| فایل/سند عملیاتی | ندارد | ندارد | `ABSENT` | ذخیره/malware-scan/retention تایید نشده |
| PDF/چاپ | ندارد | ندارد | `ABSENT` | وابسته به Invoice/سند نهایی |
| خروجی XLSX | کامل برای گزارش عملکرد | متصل | `UI_CONNECTED_LOCAL` | فقط برای گزارش‌های موجود |
| Backup/Restore دیتابیس | اسکریپت/Compose profile آماده | — | `RUNTIME_UNPROVED` | Docker/psql/`initdb` روی این هاست غایب (تایید اجرا شد) |
| Deployment profile/feature flag | مدل/کد ندارد | — | `ABSENT` | طراحی معماری تصویب نشده؛ بخش ۷ |
| Build/release/حفاظت سورس | Dockerfile hash-pinned، ولی نشتی محتوا دارد | — | نیازمند اصلاح | بخش ۹، ردیف اول (P0) |
| PostgreSQL رانتایم واقعی | تست harness آماده | — | `RUNTIME_UNPROVED` | `initdb` غایب؛ فقط SQLite محلی pass شد |
| Nginx/TLS معکوس | کانفیگ آماده، cert واقعی ندارد | — | `RUNTIME_UNPROVED` | hostname/cert/key واقعی |
| VPN/شبکه هدف | فقط طراحی توصیه‌شده در سند | — | `BLOCKED_EXTERNAL` | مدل router/ISP/VPN واقعی |
| مانیتورینگ/rollback | runbook آماده، تمرین واقعی نشده | — | `RUNTIME_UNPROVED` | owner/drill واقعی |
| یکپارچگی بیرونی (وب‌سایت/درگاه/حسابداری/ایمیل/تلفنی) | ندارد | ندارد | `BLOCKED_EXTERNAL` | مستندات رسمی provider هرکدام |

جزئیات دقیق فیلد/endpoint هر ردیف در `docs/backend/ENTITY_CATALOG.md`، `RELATIONSHIPS.md`، `API_CONTRACT.md` و `docs/frontend/FRONTEND_REFERENCE_MAP.md` نگه داشته می‌شود تا اینجا تکراری و duplicate-prone نشود.

### وضعیت اتصال frontend↔backend

ممیزی مستقل خط‌به‌خط (۲۵ route در `common/ui_urls.py`، هر ۲۵ تابع `setup*` در `kariz-app.js`، هر endpoint در پنج app) نتیجه داد: **اتصال واقعی و کامل است، نه partial و نه فقط shell.** هیچ دکمه/لینک مرده، هیچ `data-page` بی‌صاحب، هیچ fetch به مسیر ناموجود، هیچ پیام موفقیت جعلی، و هیچ قابلیت backend بدون UI متصل پیدا نشد. تنها نقص واقعی یافت‌شده یک باگ HTML کوچک است (بخش ۹).

صفحات نمایشی/فروشنده (Metronic/KeenThemes زیر `assets/`, `src/`, `dashboards/`, `pages/`, و مشابه) صرفا مرجع بصری bounded هستند، جزو اپلیکیشن served نیستند و در `.dockerignore` صریحا exclude شده‌اند — تایید شد.

## ۶. ماتریس نقش و دسترسی

| قابلیت | Sales Agent | Sales Manager | Company IT | Platform Admin |
|---|---|---|---|---|
| ورود/پروفایل خود | بله | بله | بله | بله |
| مدیریت کاربر | خیر | خیر (تا تصمیم مستقیم بعدی) | حساب‌های غیر-platform | همه هویت‌های تمیز CRM |
| اعطای نقش | خیر | خیر | تا `company_it`؛ هرگز `platform_admin` | بله، هر نقش ثابت |
| Customer/Lead/Interaction | فقط assigned/created خود | همه شرکت | همه شرکت | همه شرکت |
| Product/Category مدیریت | فقط خواندن (active) | بله | بله | بله |
| Sale ثبت/لغو | assigned Lead خود / لغو ندارد | ثبت+لغو، audited | ثبت+لغو، audited | ثبت+لغو، audited |
| After-Sales | فقط اگر workstream=`after_sales`، فقط پرونده تخصیص‌یافته | همه پرونده شرکت | همه پرونده شرکت | همه پرونده شرکت |
| گزارش عملکرد | فقط خودش | شرکت | شرکت | شرکت |
| Audit log | خیر | خیر (BIZ-011 باز) | audit غیر-platform | audit کامل |
| Django Admin/سرور | خیر | خیر | خیر (پیش‌فرض) | مسیر مدیریت جدا |

این ماتریس با enforcement واقعی در `sales/selectors.py`، `aftersales/selectors.py`، `auditlog/selectors.py` تایید شد؛ frontend فقط نمایش است و مرز امنیتی نیست.

## ۷. اصول deployment profile چندمشتری

اصول تصمیم‌شده در بخش ۲ باید در آینده به یک مدل صریح (مثلا `DeploymentProfile`/feature-flag با fail-closed روی profile ناشناخته) تبدیل شود. **این مکانیزم امروز در کد وجود ندارد** — تنها جداسازی امروز از طریق دیتابیس/تنظیمات جدا در سطح deployment (نه کد) قابل انجام است. طراحی دقیق profile، منبع feature flag، و تضمین «غیرفعال‌سازی feature داده را حذف نمی‌کند» یک آیتم Roadmap (P3) است، نه یک نقص باگ‌مانند.

## ۸. مدل تهدید حفاظت از سورس و تضمین واقع‌بینانه

مالک فیزیکی هاست (مشتری) طبق تصمیم مستقیم ممکن است دسترسی Administrator داشته باشد؛ رازداری مطلق سورس از چنین مالکی تضمین فنی ندارد. وضعیت فعلی واقعی، نه فرضی:

- **یافته پرریسک تاییدشده:** `Dockerfile` با `COPY . .` (خط ۱۵) کل build context را کپی می‌کند. `.dockerignore` مسیرهای vendor/demo، `.git`، `.env*` و فایل‌های secret-shaped را exclude می‌کند اما **`docs/**`، فایل‌های ریشه `*.md` (شامل `BACKEND_SPEC.md`، همین `KARIZ_PROJECT_HANDOFF.md` با حجم حدود ۳۰۰ کیلوبایت، `KARIZ_CLIENT1_CODEX_ROADMAP.md`)، کل `*/tests/**`، `scripts/**`، `nginx/**`، `compose*.yml`، `requirements-direct.txt` را exclude نمی‌کند.** یعنی اگر ایمیج طبق دستور مستند در `docs/ops/DEPENDENCIES.md` ساخته شود، سورس پایتون کامل خوانا (نه compiled)، کل تست‌ها، و کل اسناد برنامه‌ریزی داخلی داخل ایمیج نهایی قرار می‌گیرند و برای هرکس که ایمیج یا فایل‌سیستم هاست را ببیند قابل خواندن است.
- این نشتی توسط هیچ gate موجود پوشش داده نمی‌شود: `docs/ops/SECURITY_SCANS.md` فقط secret (Gitleaks)، آسیب‌پذیری بسته (pip-audit/Grype/SBOM) و TLS خارجی را چک می‌کند، نه محتوای فایل ایمیج. `docs/ops/RELEASE_CHECKLIST.md` فقط diff مخزن Git را review می‌کند، نه محتوای ایمیج ساخته‌شده. `docs/ops/SOURCE_MANIFEST.md` فقط تغییرات commit به commit را classify می‌کند، نه خروجی `docker build`. این یک gap مستندنشده است، نه ریسک شناخته‌شده قبلی.
- نکته مثبت تاییدشده: خود `compose.yml`/`compose.restore-verify.yml`/`compose.write-stop.yml` هیچ `build:` context ندارند (فقط `image: repo@sha256:digest` pull می‌کنند)؛ هیچ پورت PostgreSQL یا اپ مستقیما به هاست/شبکه عمومی publish نمی‌شود (فقط Nginx 80/443)؛ `restore-verify` با `network_mode: none` اجرا می‌شود. نشتی فقط در لحظه build ایمیج رخ می‌دهد، نه در هر بار اجرای Compose.
- هدف واقع‌بینانه طبق تصمیم مالک محصول: نبود repo/toolchain/تست/مستندات توسعه در تحویل، backend کامپایل/بسته‌بندی‌شده در جایی که عملی است، فرانت بدون source map، بدون کلید امضا روی هاست مشتری، بروزرسانی/rollback فقط از مسیر مالک پلتفرم. **هیچ‌کدام از این‌ها امروز پیاده نشده؛ فقط feasibility ممیزی و gate برنامه‌ریزی شد (طبق دستور صریح P0، هیچ packaging/license enforcement در این فاز اجرا نشد).**
- برندینگ/نام مشتری: تمیز. `metronic`/`keenthemes` فقط در دو assertion منفی تست (`common/tests/test_ui.py`) و در اسناد/ابزار داخلی (`scripts/check_html_branding.py`، `docs/codebase/BRANDING_CLEANUP.md`) دیده می‌شود، هرگز در خروجی served. «Client-1» فقط به‌عنوان کد داخلی پروژه در اسناد دیده می‌شود، هرگز در template/fixture/API response/نام بسته served. نام شخص‌ثالث واقعی («Satras Web»، یک theme localizer قدیمی) فقط داخل درخت vendor exclude‌شده و در regex ابزار حذف‌کننده دیده شد. هیچ source map در `common/static/common/**` نیست.

## ۹. نقص‌ها و ریسک‌های P0/P1 فعلی

| # | نقص | شدت | محل | اقدام |
|---|---|---|---|---|
| 1 | نشتی محتوای ایمیج Docker (بخش ۸) | **P0** | `Dockerfile:15`, `.dockerignore` | افزودن exclude برای `docs/`, `*.md` ریشه، `*/tests/`, `scripts/`, `nginx/`, `compose*.yml`, `requirements-direct.txt`، یا مهاجرت به multi-stage build که فقط artifact لازم را کپی کند. **این فاز آن را اصلاح نکرد** چون تغییر `Dockerfile`/`.dockerignore` تغییر رفتار build/deployment است، نه مستندسازی؛ برای فاز بعدی (Roadmap P12) ثبت شد. |
| 2 | تناقض داخلی `BACKEND_SPEC.md` بخش ۲.۳/۲.۴ (وضعیت پستی و گزارش پیامک ورودی را «blocked» می‌گفت درحالی‌که در همان سند بخش ۵.۷A/۵.۹ و در کد واقعی پیاده شده‌اند) | P1 مستندات | `BACKEND_SPEC.md` | در همین فاز اصلاح شد (بخش زیر). |
| 3 | خطای HTML: `common/templates/common/sales_documents/detail.html:16` — attribute `maxlength="500` بدون quote بسته؛ باعث می‌شود پاراگراف خطای فیلد «reason» در فرم انتقال وضعیت پستی هیچ‌وقت در DOM ساخته نشود (فقط نمایش خطای per-field تحت تاثیر است؛ ثبت واقعی وضعیت پستی درست کار می‌کند و به endpoint واقعی می‌رود) | P1 (نه امنیتی، نه از کار انداختن جریان) | `common/templates/common/sales_documents/detail.html:16` | **در این فاز اصلاح نشد** چون ویرایش template کد اپلیکیشن است، نه مستندسازی؛ برای اولین فاز مجاز اصلاح کد (P2) ثبت شد. |
| 4 | `docs/KARIZ_CAPABILITIES_FOR_INVOICE_FA.txt` (پیوست فاکتور مشتری، تاریخ ۲۰۲۶/۰۸/۱۰) نسبت به قابلیت‌های تکمیل‌شده بعدی (ProductCategory، گزارش پیامک ورودی، پنل خدمات پس از فروش) بروز نیست | P2 اسنادی | همان فایل | باید پیش از استفاده تجاری بعدی بازبینی شود؛ در این فاز تغییر نکرد چون سند دو-فایل زنده مصوب (Handoff/Roadmap) نیست. |
| 5 | عدم‌تطابق نسخه Python: هاست توسعه فعلی `Python 3.14.5` دارد؛ `Dockerfile` فقط base image با `sys.version_info[:2] == (3, 13)` را می‌پذیرد | اطلاع‌رسانی، نه نقص | `Dockerfile:12` | تست‌های محلی روی 3.14.5 pass شدند ولی رفتار دقیق production روی 3.13 محلی proof نشده؛ در build واقعی هدف تایید شود. |

## ۱۰. blockerهای بیرونی deployment (ورودی گزارش‌شده، نه fact اثبات‌شده)

- هاست گزارش‌شده «Windows Server 2008» در پرند؛ ۱۶ گیگ RAM، حدود ۲ ترابایت SSD؛ نرم‌افزار حسابداری و حداقل یک اپ دیگر روی همان هاست. **تا شواهد دقیق `winver`/`systeminfo`، Windows Server 2008/2008 R2 هدف تولید پشتیبانی‌شده تلقی نمی‌شود** و مستقیما روی آن طراحی/ادعای استقرار نمی‌شود.
- تهران و پرند ادعای IP عمومی ثابت دارند؛ مدل روتر، UPS، آنتی‌ویروس/EDR، مقصد backup، مالک restore، RPO/RTO، peak concurrency، پنجره نگهداری نامشخص‌اند.
- بدون domain/DNS عمومی تاییدشده. دسترسی بازاریاب‌ها فعلا فقط از سیستم ثابت دفتر تهران لازم است.
- هدف شبکه ترجیحی: VPN سایت-به-سایت روتر-به-روتر با HTTPS روی تونل خصوصی برای کاربران ثابت تهران؛ VPN فردی فقط برای مدیریت یا کاربران واقعا خارج از دفتر. PostgreSQL، پورت اپ، Django Admin، SSH، RDP، مدیریت کانتینر و backup service علنی نمی‌شوند (این محدودیت آخر با تنظیمات فعلی Compose تایید شد — بخش ۸).
- این‌ها همگی `BLOCKED_EXTERNAL` هستند؛ سوالات دقیق در بخش ۱۴.

## ۱۱. دستورهای دقیق و شواهد فعلی (اجراشده در همین فاز، همین هاست)

```text
git rev-parse --show-toplevel        → C:/Users/Dear-OTCamp-User/Desktop/Kariz-CRM
git rev-parse HEAD                   → 58b25a18cf8fe538710ac03521b256ca18fe3f81
git branch --show-current            → main
git status --short                   → " D AGENTS.md" (pre-existing، جزو P0 نیست)
git diff --check                     → pass (بدون whitespace)
python manage.py check --settings=config.test_settings
    → "System check identified no issues (0 silenced)."
python manage.py makemigrations --check --dry-run --settings=config.test_settings
    → "No changes detected"
python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
    → pass (نیازمند PYTHONIOENCODING=utf-8 روی این کنسول Windows؛ صرفا محدودیت encoding کنسول محلی است، نه خطای schema)
python manage.py test --settings=config.test_settings -v 1
    → "Ran 342 tests ... OK (skipped=7)"؛ ۷ skip همگی PostgreSQL-only
python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
    → exit 0، بدون خطا
node --check common/static/common/kariz-app.js
    → exit 0
python scripts/check_html_branding.py
    → "HTML_BRANDING_PASS files=228"
powershell -NoProfile -File scripts/test-postgres.ps1
    → شکست فوری: "initdb: The term 'initdb' is not recognized" — تایید می‌کند PostgreSQL native روی این هاست نصب نیست؛ RUNTIME_UNPROVED نه FAIL محصول.
which docker / which psql (bash)     → یافت نشد (تکرار همان یافته اسناد قبلی، اکنون با اجرای واقعی تایید شد)
```

هیچ نتیجه بالا جایگزین شواهد اجراشده روی محیط هدف واقعی نمی‌شود.

## ۱۲. وضعیت انتشار فعلی

`production candidate; external verification pending` — بدون تغییر نسبت به قبل، اکنون با شواهد تازه‌تر: مخزن/تست/schema/branding محلی سبز است (بخش ۱۱)، اما ایمیج immutable واقعی، PostgreSQL/Compose/Nginx زنده، TLS واقعی، backup/restore واقعی، load/scan هدف، UAT هدف و rollback drill انجام نشده و روی این هاست ابزارش موجود نیست. `NO-GO` برای هرگونه استقرار تا این فاز باقی می‌ماند. تا زمانی که یافته P0 بخش ۹ ردیف ۱ (نشتی محتوای ایمیج) اصلاح و بازبینی نشود، حتی تولید یک ایمیج «آماده انتشار» هم نباید انجام شود.

## ۱۳. فاز دقیق بعدی و اقدام دقیق ازسرگیری

فاز بعدی `P1 — بستن تصمیم‌های کسب‌وکار/دامنه باز` طبق `KARIZ_CLIENT1_CODEX_ROADMAP.md` است، مشروط به پاسخ مالک محصول به سوالات بخش ۱۴. موازی و مستقل از آن، `P2` (سخت‌سازی UI فعال و رفع کنترل مرده) می‌تواند شروع شود چون فقط یک نقص کوچک شناخته‌شده دارد (بخش ۹ ردیف ۳). اقدام دقیق ازسرگیری: مالک محصول به سوالات شماره‌گذاری‌شده در بخش ۱۴ پاسخ دهد؛ سپس با هر تصمیم مصوب، `KARIZ_CLIENT1_CODEX_ROADMAP.md` فاز مربوطه به‌روزرسانی و پیاده‌سازی محدود همان تصمیم آغاز شود. اصلاح نشتی ایمیج (بخش ۹ ردیف ۱) باید پیش از هر تلاش build ایمیج واقعی انجام شود، مستقل از تصمیم‌های کسب‌وکار.

## ۱۴. شناسه‌های تصمیم باز (شماره‌گذاری‌شده)

مصوب و بسته (فقط برای provenance، دیگر باز نیستند): نگاشت نقش‌ها/برچسب فارسی؛ نبود مدل Team برای Client 1 (Sales Manager فقط دامنه شرکت‌محور و مدیریت Sales Agent)؛ جداسازی workstream `sales`/`after_sales`.

باز — کسب‌وکار/دامنه:

1. `BIZ-001` روش تخصیص اولیه Lead.
2. `BIZ-002` فهرست نهایی وضعیت و گذار Lead.
3. `BIZ-003` گروه‌بندی outcome تماس واجد شرایط.
4. `BIZ-004` معنای دقیق KPI مشتری/نرخ تبدیل.
5. `BIZ-005` مرز دقیق مدیریت کاربر توسط Sales Manager (فراتر از Sales Agent).
6. `BIZ-006` معنای دقیق correction فروش (فراتر از cancel فعلی).
7. `BIZ-007` برچسب/قالب/تقویم جلالی خروجی XLSX.
8. `BIZ-008` گراف وضعیت/reopen/SLA خدمات پس از فروش.
9. `BIZ-009` زمان‌بندی/نگهداری/مالک/RPO/RTO backup.
10. `BIZ-010` هدف ظرفیت/بار همزمان و قانون abort.
11. `BIZ-011` مرز audit قابل‌مشاهده برای Sales Manager.
12. `BIZ-012` سیاست backfill یا رد دائمی رکوردهای audit قدیمی.
13. `BIZ-013` رفتار Lead فعال هنگام غیرفعال‌سازی کاربر مالک آن.

باز — دامنه‌های بزرگ (هرکدام باید قبل از کد شروع شود):

14. Inventory/انبار: واحد، مکان انبار، موجودی اول دوره، رزرو، منفی‌شدن، اصلاح/برگشت.
15. Order و Quotation: چرخه، منبع، تبدیل، شماره‌گذاری، تاییدها.
16. Invoice/InvoiceItem حسابداری-حقوقی: حوزه مالیاتی، نرخ، ترتیب تخفیف، رُند کردن، شماره‌گذاری، اصلاح/ابطال، snapshot.
17. Payment، چک، قسط: روش‌ها، تخصیص، idempotency، reversal/refund، تطبیق.
18. حساب/دفتر مشتری (Customer Ledger): قرارداد بدهکار/بستانکار، موجودی اول دوره، تعدیل.
19. مطالبات و سود/زیان: فرمول دقیق، منبع هزینه/موجودی، دوره بستن.
20. فایل/سند عملیاتی: نوع/حجم مجاز، نگهداری، دانلود، malware scan.
21. یکپارچگی‌های بیرونی (وب‌سایت/فروشگاه/درگاه/حسابداری/ایمیل/پیامک/تلفنی): provider دقیق، مستندات رسمی، credential، owner، retry/reconciliation.

باز — استقرار/زیرساخت (پاسخ مالک محصول یا صاحب زیرساخت لازم است):

22. شواهد دقیق `winver` و `systeminfo` هاست پرند؛ آیا «Windows Server 2008» نسخه OS است یا SQL Server یا نرم‌افزار حسابداری؟
23. ادیشن Windows، Service Pack، معماری، ظرفیت مجازی‌سازی.
24. مدل/برند/firmware روتر تهران و پرند.
25. دامنه Active Directory در برابر دامنه اینترنتی عمومی؛ مالکیت DNS.
26. تصمیم مصوب: سرور/appliance اختصاصی پشتیبانی‌شده یا ارتقای OS پشتیبانی‌شده؟
27. تعداد کل و peak همزمان کاربران مورد انتظار.
28. وضعیت UPS و endpoint security/antivirus.
29. مقصد backup خارج از سایت و مقصد همیشه-روشن تهران؛ مالک نگهداری/بازیابی/حادثه؛ پنجره نگهداری.
30. نمونه فاکتور/PDF ردشده (redacted) برای تایید قالب.
31. تایید نهایی حفاظت سورس/امضای release و سیاست تجاری پشتیبانی/بروزرسانی.

باز — حاکمیت مستندات (تولید همین فاز):

32. آیا `AGENTS.md` (حذف‌شده از working tree پیش از این نشست، هنوز در Git history موجود است) بازگردانده شود، یا با یک `CLAUDE.md` مختصر جایگزین شود؟ توصیه بخش پاسخ نهایی را ببینید.
33. آیا تعریف/پیاده‌سازی مدل `DeploymentProfile`/feature-flag (بخش ۷) به‌عنوان اولین قدم فنی، مستقل از تصمیم‌های کسب‌وکار بزرگ‌تر، اکنون آغاز شود؟
