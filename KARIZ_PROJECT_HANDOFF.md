# Kariz CRM project handoff

این فایل تنها منبع زنده وضعیت، پیشرفت، blocker، شاهد و تصمیم باز پروژه است. `BACKEND_SPEC.md` قرارداد normative پیاده‌سازی است؛ `docs/backend/*.md` قراردادهای فنی جزئی، `docs/ops/*.md` runbookهای عملیاتی، و `KARIZ_CLIENT1_CODEX_ROADMAP.md` نقشه فازبندی‌شده است. هیچ‌کدام جایگزین وضعیت زنده همین فایل نیستند. سوابق checkpoint قدیمی‌تر از این بازنویسی (P0 — ۲۰۲۶/۰۸/۱۴) در `git log` و در تاریخچه همین فایل قابل بازیابی است؛ اینجا فقط نتیجه نهایی و شواهد فعلی نگه داشته می‌شود.

## ۰.۰۰ فاز `P0R.2` — اجرای واقعی روی PostgreSQL 17.11 — **`P0R.2 BLOCKED`** روی یک گام باقی‌مانده (۲۰۲۶/۰۸/۱۵)

باینری‌های PostgreSQL 17.11 توسط مالک محصول در `C:\Users\Dear-OTCamp-User\pgsql-17.11` تامین شدند (فقط محیط توسعه؛ **قرارداد تولید نیست**). هر هشت باینری اجرا و نسخه‌شان تایید شد: `postgres`، `initdb`، `pg_ctl`، `psql`، `createdb`، `pg_dump`، `pg_restore`، `pg_isready` — همگی `17.11`. فایل‌های `share` (`postgres.bki`، `postgresql.conf.sample`، `pg_hba.conf.sample`) موجود و توسط `initdb` قابل یافتن‌اند.

### نتیجه اصلی: اپلیکیشن روی PostgreSQL واقعی کار می‌کند

اولین اجرای مجموعه روی PostgreSQL: **۱۰ failure و ۱۸ error**. پس از اصلاح، **۴۰۴ تست، `OK`، ۶ skip**. روی SQLite هم **۴۰۴ تست، `OK`، ۷ skip**. هیچ‌کدام از نقص‌ها در اپلیکیشن نبود — همه در تست یا تنظیمات تست بودند و **هیچ migration مخزن ساخته نشد** (`makemigrations --check` تمیز). یک دیتابیس تازه از migrationها صحیح ساخته می‌شود (مستقیما بازرسی شد: `postal_code` موجود، هر ۱۳ migration اپ `sales` اعمال).

### هر ۷ تست PostgreSQL-only اکنون اجرا و pass می‌شوند

```text
test_cancel_race_has_one_transition_and_one_audit_row          ok
test_global_active_phone_identity_wins_once                    ok
test_last_platform_admin_guard_is_serialized                   ok
test_reassignment_and_sale_use_one_lead_order                  ok
test_sale_price_snapshot_is_linear_with_product_update         ok
test_sales_upgrade_from_0004_keeps_valid_business_rows         ok
InboundSMS test_concurrent_same_event_creates_one_row          ok
Ran 7 tests — OK
```

این proof همزمانی واقعی است: قفل ردیف (`select_for_update`)، ترتیب قفل lead/sale، رقابت یکتایی شماره تلفن، سریال‌سازی نگهبان آخرین Platform Admin، idempotency پیامک، و upgrade واقعی migration از 0004.

### چهار نقص کشف‌شده — همگی TEST_BUG، نه اپلیکیشن

1. **مسموم‌سازی schema (شدید).** `PostgresMigrationUpgradeTests` اپ `sales` را به 0004 برمی‌گرداند و فقط تا 0010 جلو می‌برد — حتی در `finally`. چون `TransactionTestCase` است، schema برنمی‌گردد و **هر تست بعدی** دیتابیسی بدون `postal_code` و بدون جداول 0011-0013 می‌دید. برگرداندن `sales` همچنین migrationهای وابسته (`aftersales`، `communications`) را unapply می‌کند، پس بازیابی اکنون leaf همه اپ‌ها را هدف می‌گیرد. روی SQLite این تست همیشه skip بود و باگ نامرئی مانده بود.
2. **`ENABLE_API_DOCS` غایب** در `config/postgres_test_settings.py` (در `test_settings` هست) → مسیرهای schema/docs ثبت نمی‌شدند و ۷ تست system-API فقط به‌خاطر ماژول تنظیمات ۴۰۴ می‌گرفتند.
3. **گیت دیتابیس `seed_synthetic_uat`** روی PostgreSQL فقط `uat_kariz_*` را می‌پذیرد؛ دیتابیس harness `test_kariz_*` است، پس دستور **درست** آن را رد می‌کند. پنج تست به دیتابیس seed-pذیر محدود شدند؛ **گیت تولید تضعیف نشد** و خودش با `test_database_identity_guard_is_narrow` روی هر vendor پوشش دارد.
4. **رقابت (race) در تست‌های مرورگر.** هر صفحه handler دیالوگ را فقط **پس از** resolve شدن بارگذاری اولیه API متصل می‌کند؛ روی SQLite این میکروثانیه است، ولی تاخیر واقعی دیتابیس باعث می‌شد کلیک زودتر برسد و بی‌صدا دور ریخته شود. تست‌ها اکنون تا باز شدن واقعی دیالوگ کلیک را تکرار می‌کنند. (نکته محصولی، نه نقص: دکمه‌ای که ~۲۰۰ms ابتدای بارگذاری بی‌اثر است.)

### تفاوت‌های واقعی SQLite/PostgreSQL که مشاهده شد

- **طول `varchar` اجرا می‌شود.** درج `notes` بلندتر از حد در PostgreSQL `DataError: value too long for type character varying(4000)` می‌دهد؛ SQLite کاملا نادیده می‌گیرد. نتیجه مثبت برای تولید: ردیف بیش‌ازحد بلند اصلا نمی‌تواند وجود داشته باشد.
- **تاخیر واقعی** (~۵۰-۱۶۰ms برای هر فراخوان API در برابر میکروثانیه) رقابت‌های زمان‌بندی فرانت را آشکار می‌کند.
- **وضعیت schema بین تست‌ها پایدار است** و `TransactionTestCase` آن را برنمی‌گرداند — روی SQLite چون تست migration اصلا اجرا نمی‌شد پنهان بود.
- قفل‌گذاری/تراکنش/یکتایی: هر ۷ probe همزمانی مطابق انتظار رفتار کردند.

### proof سلامت/آمادگی (اجراشده)

```text
دیتابیس سالم      → GET /api/v1/health/ready/  200  {"status":"ok","database":"up"}
دیتابیس خاموش     → GET /api/v1/health/ready/  503  {"status":"unavailable","database":"down"}
بررسی نشت اعتبارنامه در پاسخ/خروجی → هیچ ماده اعتبارنامه‌ای دیده نشد
```

### proof مرورگر روی PostgreSQL

ماتریس مرورگر داخل همان اجرای PostgreSQL اجرا شد (نه SQLite) و پس از رفع رقابت pass شد. پس `POSTGRES_BROWSER_UNPROVED` **دیگر برقرار نیست**.

### گام باقی‌مانده و **blocker دقیق**

مراحل bootstrap نقش‌ها → contract → dump → **restore** اجرا نشدند، چون `scripts/bootstrap-postgres.sh` در تابع `set_role_password` از دستور تعاملی `psql \password` استفاده می‌کند. روی این هاست ویندوز آن دستور ورودی pipe شده را نادیده می‌گیرد و برای همیشه منتظر کنسول می‌ماند.

با آزمایش ایزوله قطعی اثبات شد:

```text
printf 'pw\npw\n' | psql ... -c "SET password_encryption='scram-sha-256'" -c "\password role"
→ TIMED OUT (بلوکه)
pg_stat_activity: state=idle, wait_event=Client/ClientRead,
                  query="SET password_encryption = 'scram-sha-256'"
```

طبقه‌بندی: **`ENVIRONMENT_BUG` / محدودیت قابل‌حمل‌بودن** — نه نقص تولید. هدف تولید کانتینر لینوکسی است و آنجا `\password` با stdin لوله‌شده درست کار می‌کند. در اجراهای قبلی این مرحله هرگز اجرا نشده بود چون harness زودتر روی شکست تست متوقف می‌شد.

**این تغییر داده نشد.** `bootstrap-postgres.sh` اسکریپت bootstrap تولید (`db-bootstrap` در Compose) و امنیت-حساس است؛ `\password` عمدا انتخاب شده تا رمز به‌صورت plaintext به سرور/لاگ نرود. تغییر آن یک تصمیم مالک محصول است، نه حدس من.

### گیت‌های مخزن (SQLite)

```text
check → 0 | makemigrations --check → No changes detected | spectacular → 0
collectstatic → 0 | branding → PASS files=228 | node --check → 0
validate_image_content --context → PASS | git diff --check → 0
manage.py test → Ran 404 tests, OK (skipped=7)
```

### پاکسازی

هیچ cluster موقت، هیچ فرآیند `postgres`/`psql`، و هیچ پوشه `kariz-pgtest-*` باقی نماند (تایید شد). درخت کاری تمیز.

## ۰.۰ تلاش قبلی فاز `P0R.2` — **`BLOCKED_ENVIRONMENT`** (۲۰۲۶/۰۸/۱۵، منسوخ‌شده توسط بخش بالا)

هدف این فاز اثبات اپلیکیشن روی PostgreSQL واقعی به‌جای SQLite بود. **هیچ بخشی از این proof اجرا نشد** چون PostgreSQL روی ماشین توسعه نصب نیست. طبق سیاست، نرم‌افزار سیستمی بدون اجازه صریح نصب نشد.

### جست‌وجوی جامع (نه فرض)

`psql`، `pg_dump`، `pg_restore`، `initdb`، `pg_isready`، `pg_ctl`، `createdb`، `postgres` و `docker` — همگی غایب. علاوه بر `PATH`: هیچ سرویس ویندوزی با نام `*postgres*`، هیچ رکورد registry (`PostgreSQL`/`pgAdmin`/`EnterpriseDB`)، کلید `HKLM:\SOFTWARE\PostgreSQL` غایب، مسیرهای استاندارد نصب و مسیرهای scoop/chocolatey غایب، و جست‌وجوی بازگشتی `psql.exe` روی درایو `C:` بدون نتیجه.

### قرارداد نسخه (از خود مخزن، نه از عادت)

`docs/ops/DEPLOYMENT.md` صریحا **PostgreSQL 17** را برای سرویس `db` تعیین می‌کند. ایمیج Compose با digest قفل است (`KARIZ_POSTGRES_IMAGE`)، پس digest قرارداد انتشار است نه tag. `psycopg[binary]==3.2.13` محدودیت باریک‌تری تحمیل نمی‌کند.

### baseline SQLite (اجراشده)

`389` تست، `OK`، `7` skip. هر ۷ skip دقیقا همان تست‌های PostgreSQL-only هستند و **تنها شرط skip آن‌ها `connection.vendor == "postgresql"` است** — هیچ شرط دیگری ندارند، پس روی PostgreSQL قطعا اجرا خواهند شد:

```text
common.tests.test_postgres_concurrency.PostgresConcurrencyTests
    test_cancel_race_has_one_transition_and_one_audit_row
    test_global_active_phone_identity_wins_once
    test_last_platform_admin_guard_is_serialized
    test_reassignment_and_sale_use_one_lead_order
    test_sale_price_snapshot_is_linear_with_product_update
common.tests.test_postgres_concurrency.PostgresMigrationUpgradeTests
    test_sales_upgrade_from_0004_keeps_valid_business_rows
communications.tests.test_sms.InboundSMSConcurrencyTests
    test_concurrent_same_event_creates_one_row
```

### ممیزی ایمنی harness (ایستا — قبول)

`scripts/test-postgres.ps1` پیش از هر تلاش اجرا کامل خوانده شد. نمی‌تواند به دیتابیس تولید یا هر سرور موجود برسد: با `initdb` یک cluster یک‌بارمصرف تازه در temp می‌سازد (به سرور موجود وصل نمی‌شود)؛ مسیر داده باید با پیشوند `kariz-pgtest-<guid>` مطابقت کند و این هم پیش از ساخت و هم پیش از حذف بررسی می‌شود و در غیر این صورت throw می‌کند؛ فقط `127.0.0.1` روی یک پورت بالای تصادفی bind می‌شود و پورت ۵۴۳۲ و ≤۱۰۲۴ صریحا رد می‌شوند؛ نام دیتابیس/نقش/رمز همگی به run token تصادفی گره خورده‌اند؛ `config/postgres_test_guard.py` مستقلا همه این‌ها را دوباره اعتبارسنجی می‌کند و fail-closed است؛ هر متغیر محیطی و `PATH` در `finally` بازگردانده می‌شود و هیچ رمزی چاپ نمی‌شود.

با اجرا تایید شد: در نبود ابزار، harness در مرحله تشخیص ابزار متوقف می‌شود (`CommandNotFoundException` روی `initdb`) و **به هیچ سرور دیگری fallback نمی‌کند**.

### شکاف پوشش کشف‌شده حین ممیزی

harness فقط ثابت می‌کند نقش backup می‌تواند `pg_dump` بگیرد؛ **هرگز `pg_restore` را صدا نمی‌زند**. تنها تاییدکننده restore یعنی `scripts/verify-postgres-restore.sh` وابسته به کانتینر است (مسیرهای ثابت `/backups` و `/ops` و sentinel `.kariz-backup-root`) و روی ویندوز به‌صورت native اجرا نمی‌شود.

یعنی حتی پس از نصب PostgreSQL، نیمه «restore ایزوله» از گیت P0R.2 به یکی از این دو نیاز دارد: Docker به‌همراه profile `restore-verify`، یا افزودن یک گام restore native کوچک به harness (`createdb` دوم، `pg_restore`، سپس اجرای `verify-postgres-schema.sql` روی آن). این یک شکاف ابزار است، نه نقص اپلیکیشن.

### مسیر رفع انسداد

harness پارامتر `-PostgresBin` دارد، پس نصب کامل لازم نیست: کافی است آرشیو باینری‌های PostgreSQL 17 ویندوز هرجا استخراج شود و مسیر `bin` آن پاس داده شود. این روش هیچ سرویس، رکورد registry یا دسترسی administrator لازم ندارد. یک VM توسعه یک‌بارمصرف هم قابل قبول است.

### نتیجه گیت‌ها در این تلاش

migration روی PostgreSQL، اجرای مجموعه تست روی PostgreSQL، proof همزمانی، proof قید/یکپارچگی، proof نقش‌های دیتابیس، dump و restore — **هیچ‌کدام اجرا نشدند**. هیچ ادعای موفقیتی برای آن‌ها ثبت نمی‌شود.

## ۰. ممیزی حقیقت رانتایم و اتصال UI↔backend — ۲۰۲۶/۰۸/۱۵

هدف این فاز پاسخ به یک پرسش مشخص مالک محصول بود: آیا فرانت واقعا به backend وصل است و آنچه ادعا شده واقعا کار می‌کند؟ پاسخ با **اجرای واقعی** به‌دست آمد، نه با خواندن کد یا اعتماد به prose.

- HEAD: `5efe1c8f9ba2b083268cbb006208bd294807ed97`، شاخه `main`، درخت کاری در شروع و پایان **تمیز**. (HEAD مورد انتظار در درخواست `7a4ca14` بود؛ آن اکنون والد HEAD فعلی است — کار فاز قبلی commit و push شده است.)

### شاهد قاطع: تست مرورگر واقعی اجرا شد و **۱۷/۱۷ pass** شد

برخلاف فرض «BROWSER_RUNTIME_UNPROVED»، هارنس Selenium روی همین هاست کار می‌کند (Selenium 4.21.0 + Chrome نصب). هر پنج ماژول تست مرورگر اجرا شد:

```text
test_auth_shell_browser        4/4 ok
test_sales_shell_browser       6/6 ok
test_after_sales_browser       1/1 ok
test_sms_shell_browser         2/2 ok
test_synthetic_uat_browser     4/4 ok   (هر چهار پرسونای UAT)
Ran 17 tests in 67.057s — OK
```

این پوشش شامل ورود/خروج، ناوبری موبایل، داشبورد نقش‌محور، چرخه مشتری→lead→تخصیص→تماس، دسته/کالا، فروش، سند پستی، خدمات پس از فروش، گزارش پیامک و drill-down است. **بنابراین ادعای «UI متصل است» دیگر ادعای مستند نیست، شاهد اجراشده است.**

### ممیزی authorization با probe اجراشده (نه خواندن کد)

یک probe موقت نوشته و اجرا شد، سپس حذف شد (درخت تمیز ماند). نتایج دقیق:

```text
PROBE manager_create              status=201  created_role=sales_agent
PROBE manager_reset_password      status=200  password_changed=True
PROBE manager_change_workstream   status=200  workstream=after_sales
PROBE manager_deactivate          status=200  is_active=False
PROBE manager_vs_platform         get=404 patch=404 change_role=404  platform_still_active=True
PROBE manager_self_escalation     status=404  role_now=sales_manager

PROBE agent_a_reads_customer_of_agent_b   status=404
PROBE agent_a_reads_lead_of_agent_b       status=404
PROBE agent_a_reads_sale_of_agent_b       status=404
PROBE agent_a_edits_customer_of_agent_b   status=404  name_now='B customer'
PROBE agent_a_customer_list  count=0  contains_b_customer=False
PROBE agent_gets_users=403  activity_logs=403  inbound_sms_report=403
PROBE after_sales_operator_gets customers/leads/sales = 200 با rows=0؛ direct-ID = 404
```

نتیجه‌گیری دقیق:

- **هیچ IDOR و هیچ privilege escalation پیدا نشد.** دسترسی با ID مستقیم بین دو بازاریاب کاملا ۴۰۴ است، هم خواندن هم نوشتن. مدیر فروشگاه نه می‌تواند platform admin را ببیند، نه تغییر دهد، نه نقش خودش را ارتقا دهد.
- **ساخت کاربر توسط مدیر فروشگاه امن است:** نقش کاربر ساخته‌شده همیشه `sales_agent` است. `role` در چهار لایه مسدود است (`server_fields`، `read_only_fields`، `USER_MUTABLE_FIELDS`، و default مدل). این یک مسیر escalation **نیست**.
- **شکاف واقعی `BIZ-005` دقیقا این است و نه بیشتر:** مدیر فروشگاه می‌تواند حساب `sales_agent` بسازد، ویرایش کند، **رمز را reset کند**، **workstream را تغییر دهد**، و غیرفعال/فعال کند. این‌ها با سیاست بسته Client 1 مغایرند و کار فاز `P1.7` هستند.

### یافته جدید — Django Admin در شبکه باز است (MEDIUM)

`config/urls.py:11` مسیر `admin/` را **بدون هیچ شرطی** ثبت می‌کند — برخلاف `ENABLE_API_DOCS` که پشت گیت تنظیمات است. `nginx/default.conf:111` هم `/admin/login/` را (با rate limit) proxy می‌کند نه مسدود.

probe اجراشده:

```text
PROBE admin_login_page_anonymous       status=200
PROBE platform_admin is_staff=False is_superuser=False
PROBE platform_admin_django_login=True admin_index_status=302
PROBE platform_admin_admin_login_post  status=200 (رد شد، redirect نشد)
```

تفسیر صادقانه: صفحه ورود ادمین در دسترس شبکه است، **اما هیچ هویت CRM نمی‌تواند وارد آن شود** چون همه `is_staff=False` هستند و این در `crm_identities` اجبار شده. پس این یک نشت داده نیست؛ یک سطح حمله اضافی و fingerprinting نسخه Django است. سیاست مستند Client 1 («Django Admin نباید در معرض کاربر مشتری باشد») هنوز کاملا در کد اجرا نشده است.

### نقص فعال UI — **در فاز `P2` برطرف شد (۲۰۲۶/۰۸/۱۵)**

`common/templates/common/sales_documents/detail.html:16` صفت `maxlength="500` را بدون کوتیشن بسته داشت — **تنها خط با کوتیشن نامتوازن در کل UI served**. تجزیه صفحه واقعا render شده (نه فقط قطعه کد) این خروجی را داد:

```text
<input id='postal-reason' name='reason'
       maxlength='500><p class='  field-error"=None  data-error-for='reason'>
```

**اثر واقعی — یک مورد، نه دو مورد:**

عنصر `<p class="field-error" data-error-for="reason">` **اصلا ساخته نمی‌شد**؛ صفت `data-error-for` روی خودِ `<input>` می‌نشست به‌همراه یک صفت زائد `field-error"`. `showError` آن را با `querySelectorAll("[data-error-for]")` پیدا می‌کرد و `textContent` می‌نوشت — ولی `textContent` روی `<input>` چیزی نمایش نمی‌دهد. پس خطای سمت سرور فیلد «دلیل» هرگز به کاربر نشان داده نمی‌شد.

**تصحیح یک ادعای قبلی:** ممیزی پیشین ادعا کرده بود اثر دومی هم وجود دارد و «`maxlength` از کار می‌افتد». **این ادعا نادرست بود** و با اندازه‌گیری در Chrome واقعی رد شد:

```text
PROBE_DEFECTIVE  maxLength=500  attr='500><p class='  err_p=0  input_has_dataerror='reason'
```

مرورگر `maxlength` را با «rules for parsing non-negative integers» می‌خواند که در اولین کاراکتر غیررقمی متوقف می‌شود، پس مقدار همچنان `500` بود و محدودیت ۵۰۰ کاراکتری **از کار نیفتاده بود**. فقط ادعای اثر اول درست بود. (منبع این تصحیح: اجرای واقعی، نه بازخوانی prose.)

**اصلاح انجام‌شده:** فقط یک کوتیشن بسته اضافه شد. بدون تغییر endpoint، API، مدل، serializer، قانون کسب‌وکار، CSS یا واژگان فارسی.

**پوشش رگرسیون:** `common/tests/test_sales_shell.py::SalesDocumentFormMarkupTests` (۴ تست، تجزیه DOM صفحه render شده) و `common/tests/test_sales_shell_browser.py::test_postal_reason_field_has_its_own_error_target_and_length_limit` (Chrome واقعی). هر دو با برگرداندن موقت template به حالت معیوب اجرا شدند و **fail شدند** (۴/۴ و ۱/۱)، پس پوشش واقعی است نه تزئینی. تست مرورگر یک ۴۰۰ واقعی از API را provoke می‌کند (`reason` با ۵۰۱ کاراکتر که از طریق JS مقداردهی می‌شود، چون `maxlength` فقط تایپ را محدود می‌کند نه انتساب برنامه‌ای) و ثابت می‌کند پیام خطا داخل همان `<p>` مقصد render می‌شود و وضعیت پستی سند تغییر نمی‌کند.

**بازبینی هم‌خانواده:** هر ۲۸ template served با پارسر HTML بررسی شد — صفر کوتیشن نامتوازن، صفر مقدار صفت حاوی `<`/`>`، صفر صفت زائد. هیچ نمونه دیگری از این کلاس نقص وجود ندارد.

### وضعیت کنترل‌های مرده/نمایشی — تمیز

جست‌وجوی الگویی در کل `common/templates/common/**`:

```text
href="#"            → 1 مورد، و مرده نیست (kariz-app.js:787 آن را مقداردهی می‌کند)
javascript:void(0)  → صفر
form بدون action    → صفر
action=""           → صفر
data-kt-* / KTMenu / KTDrawer / KTUtil → صفر در UI served
```

یعنی UI نگهداری‌شده هیچ ارثی از کنترل‌های نمایشی Metronic ندارد؛ کاملا first-party است. درخت vendor فقط مرجع بصری است و در `.dockerignore` هم exclude شده.

### Persian/RTL

`common/templates/common/base.html:3` = `<html lang="fa" dir="rtl">`. اسکن متن انگلیسی قابل‌مشاهده در templateهای served: صفر مورد. `check_html_branding.py` روی ۲۲۸ فایل pass.

### ماتریس اتصال UI↔backend

سند `docs/frontend/FRONTEND_REFERENCE_MAP.md` از قبل ماتریس کامل (route → template → JS handler → endpoint واقعی → نقش/scope) را برای هر ۲۵ صفحه دارد و با بررسی این فاز مطابقت داشت. **سند جدیدی ساخته نشد** تا رجیستر دوم به وجود نیاید؛ همان سند مرجع ثابت است و این فایل تنها منبع وضعیت زنده.

شمارش مسیرهای ثبت‌شده: ۱۵۲ کل = ۱۱۱ زیر `/api/`، ۲۵ صفحه UI اول‌شخص، ۱۶ مسیر `/admin/`.

### گیت‌های اجراشده این فاز

```text
python manage.py check                                  exit=0  no issues
python manage.py makemigrations --check --dry-run       exit=0  No changes detected
python manage.py spectacular --validate --fail-on-warn  exit=0
python manage.py collectstatic --dry-run --noinput      exit=0
python scripts/check_html_branding.py                   exit=0  files=228
node --check common/static/common/kariz-app.js          exit=0
python scripts/validate_image_content.py --context      exit=0  files=147 PASS
git diff --check                                        exit=0
python manage.py test                                   Ran 356 tests — OK (skipped=7)
تست‌های مرورگر (۵ ماژول)                                 Ran 17 tests — OK
```

هر ۷ skip تاییدا PostgreSQL-only هستند («PostgreSQL concurrency proof runs in the isolated PostgreSQL harness»). PostgreSQL/Docker روی این هاست نیست → `RUNTIME_UNPROVED`، نه شکست محصول.

### تغییر وضعیت نسبت به قبل

ردیف‌های `UI_CONNECTED_LOCAL` در بخش ۵ اکنون شاهد مرورگر واقعی هم دارند. با این حال هیچ‌کدام `VERIFIED_END_TO_END` نمی‌شوند، چون آن برچسب طبق تعریف خودِ این سند نیازمند proof روی رانتایم هدف (PostgreSQL/Compose/TLS/هاست واقعی) است که هنوز وجود ندارد. وضعیت انتشار `NO-GO` بدون تغییر است.

## ۰.۱ عکس فوری — ۲۰۲۶/۰۸/۱۵ — اجرای موازی P0R.1 تا P0R.4 و P1

- HEAD پایه این فاز: `7a4ca14f6417c325440e117a9576481ce5dac4ba` («Refactor project documentation and introduce repository rules» — commit فاز P0R، که پس از بازبینی انسانی ثبت شد). شاخه `main`. درخت کاری پیش از این فاز تمیز بود.
- پنج فاز موازی آغاز شدند. وضعیت واقعی هرکدام:

| فاز | وضعیت | خروجی |
|---|---|---|
| `P0R.4` سخت‌سازی build-context | **تکمیل تا سقف این هاست** | `.dockerignore` اصلاح‌شده، `scripts/validate_image_content.py`، `common/tests/test_image_content.py` |
| `P0R.3` طراحی deployment-profile | **مقایسه تکمیل شد؛ منتظر انتخاب مالک محصول** | `docs/backend/DEPLOYMENT_PROFILE_OPTIONS.md` |
| `P0R.1` survey زیرساخت | `BLOCKED_EXTERNAL` — ابزار پرسش آماده شد | `docs/ops/TARGET_SITE_SURVEY.md` |
| `P0R.2` PostgreSQL زودهنگام | **`BLOCKED_ENVIRONMENT`** — تلاش اجرا در ۲۰۲۶/۰۸/۱۵ انجام شد و شکست خورد چون PostgreSQL نصب نیست؛ جزئیات زیر | `docs/backend/POSTGRES_TESTING.md` |
| `P1` بستن تصمیم‌ها | منتظر پاسخ مالک محصول — پرسش‌ها دقیق و پاسخ‌پذیر شدند | `docs/backend/OPEN_BUSINESS_DECISIONS.md` |

### نتیجه P0R.4 — نشتی build-context بسته شد (با شاهد اجراشده)

اندازه‌گیری واقعی با شبیه‌سازی `COPY . .` روی همین مخزن:

```text
.dockerignore قبلی (در HEAD)  → 408 فایل، 142 مورد ممنوعه → IMAGE_CONTENT_FAIL
.dockerignore اصلاح‌شده        → 147 فایل، صفر مورد ممنوعه → IMAGE_CONTENT_PASS
```

۶۳٪ کاهش محتوای ارسالی. آنچه اکنون داخل context می‌ماند دقیقا این است: هفت اپ first-party + `config` + `manage.py` + `requirements.txt` + ۲۰ فایل migration. هیچ `docs/`، هیچ `*.md` ریشه، هیچ `*/tests/`، هیچ `scripts/`، `nginx/`، `compose*.yml`، `requirements-direct.txt`، source map یا bytecode.

**یافته دوم (از پیش موجود، تازه کشف‌شده):** الگوهای `__pycache__`، `*.pyc` و `*.log` در `.dockerignore` قبلی فقط root-anchored بودند — در معنای Docker یک `*` هرگز از `/` عبور نمی‌کند، پس `accounts/__pycache__/...` اصلا exclude نمی‌شد و bytecode ماشین توسعه‌دهنده وارد ایمیج می‌شد. فرم‌های بازگشتی `**/__pycache__`، `**/*.pyc`، `**/*.log` اضافه شدند (این تنها دلیل کاهش ۲۶۴ → ۱۴۷ است).

**مرز صداقت این نتیجه:** این proof مربوط به **تعریف build** است، از راه شبیه‌سازی قواعد `.dockerignore` روی درخت واقعی مخزن. هیچ ایمیج Docker ساخته یا extract نشد (Docker روی این هاست نیست). validator برای همین حالت دوم هم آماده است (`--listing`) و باید در اولین هاست دارای Docker روی ایمیج واقعی اجرا شود. همچنین این کار **منطق کسب‌وکار پایتون خوانا را پنهان نمی‌کند** — بسته‌بندی/کامپایل backend همچنان گیت جدای P12 است.

### وضعیت انتشار پس از این فاز

`NO-GO` بدون تغییر. اما یک مانع مشخص برداشته شد: پیش از این، تعریف build به‌گونه‌ای بود که هیچ ایمیجی نباید ساخته می‌شد؛ اکنون تعریف build از گیت محتوای خودش عبور می‌کند و ساخت یک ایمیج آزمایشی روی هاست دارای Docker مجاز است — مشروط به اجرای `--listing` روی همان ایمیج.

## ۱. عکس فوری وضعیت — ۲۰۲۶/۰۸/۱۴ — فاز اصلاحی P0R

- ریشه مخزن: `C:\Users\Dear-OTCamp-User\Desktop\Kariz-CRM`. شاخه: `main`. **HEAD واقعی الان: `122b4707bbdd92c095fe85917cdb4ed72c66083d`** («chore: remove AGENTS.md as part of repository cleanup»)، یک commit جلوتر از `fde384a`.
- `fde384a` («docs: reconcile client 1 scope and repository truth») commit مستندسازی فاز P0 است — همان فازی که این سند، Roadmap، و اصلاح هدفمند `BACKEND_SPEC.md` را نوشت. آن commit سه فایل را تغییر داد: `BACKEND_SPEC.md` (+۵۰/-)، `KARIZ_CLIENT1_CODEX_ROADMAP.md` (۱۵۹۰ خط کاهش خالص)، `KARIZ_PROJECT_HANDOFF.md` (۲۷۸۸ خط کاهش خالص) — جمعا ۴۶۳ افزوده و ۳۹۶۵ کاسته نسبت به نسخه پیشین.
- **فاز فعلی: `P0R` — اصلاح مستندات پیش از هر پیاده‌سازی feature.** این فاز فقط مستندات را اصلاح می‌کند (`BACKEND_SPEC.md`، همین فایل، Roadmap، و افزودن `CLAUDE.md`)؛ هیچ کد اپلیکیشن، migration، وابستگی، تست، Dockerfile یا Compose تغییر نکرد؛ هیچ `git add`/`commit`/`push` در این فاز اجرا نشد — کل diff برای بازبینی انسانی در working tree باقی می‌ماند.
- `git status --short` فعلی (بعد از commit مستقل `AGENTS.md`) **خالی است** — درخت پیش از این فاز کاملا تمیز بود؛ حذف `AGENTS.md` کار از پیش موجود و عمدی کاربر بود و در این فاز بازگردانده نشد.
- **اصلاح:** عکس فوری قبلی این بخش HEAD `58b25a1` را به‌عنوان HEAD «فعلی» معرفی می‌کرد. آن دیگر درست نیست — `58b25a1` والد `fde384a` است و `fde384a` خودش والد HEAD فعلی (`122b470`) است. این خودش یک نمونه دیگر از «prose در برابر شاهد اجراشده» است که این فاز اصلاحی موظف به رفع آن بود.
- `docs/ops/SOURCE_MANIFEST.md` و `docs/ops/RELEASE_NOTES.md` یک reference منجمد و تاریخی روی commitهای بسیار قدیمی‌تر (`50a978a`، `95dbc71e`) دارند؛ هر دو commit در تاریخچه واقعی مخزن موجودند ولی به‌شدت عقب‌تر از HEAD فعلی هستند. آن دو سند صریحا خود را «historical, not live status» اعلام می‌کنند؛ به‌عنوان شاهد وضعیت فعلی استفاده نشوند. از زمان آن reference هیچ immutable release reference تازه‌ای تولید نشده است.

## ۲. تصمیم‌های مستقیم کاربر که اکنون معتبرند

این‌ها تصمیم مالک محصول برای برنامه‌ریزی هستند و بر prose قدیمی هر سند دیگر اولویت دارند:

- محصول Kariz CRM / کاریز؛ رابط کاربر نهایی نگهداری‌شده فارسی-only، RTL، responsive و same-origin است. Monolith ماژولار می‌ماند مگر کد موجود خلاف آن را ثابت کند (کد فعلی این‌طور است: یک Django project با appهای `accounts/sales/aftersales/communications/auditlog/reports/common`، بدون microservice).
- یک کدبیس مشترک برای چند استقرار مشتری؛ فورک یا شاخه دائمی مشتری‌محور ممنوع؛ هر استقرار DB/secret/runtime identity/backup/branding/feature-profile جدا دارد؛ `if client_name == ...` در کد پخش نشود؛ فعال/غیرفعال بودن feature از role permission و object scope جدا است؛ غیرفعال‌کردن feature داده تاریخی را پاک نمی‌کند؛ profile یا dependency ناشناخته fail-closed است. **وضعیت فعلی کد: هیچ مدل/مکانیزم DeploymentProfile یا FeatureFlag در کد وجود ندارد (تایید شد — هیچ چنین کلاسی در هیچ app پیدا نشد). این یک اصل تاییدشده برای طراحی آینده است، نه یک قابلیت پیاده‌سازی‌شده.** به بخش ۷.
- **نقش‌های ثابت Client 1 — سیاست نهایی، بسته (`BIZ-005` resolved، ۲۰۲۶/۰۸/۱۴):** کد فعلی دقیقا همین چهار نقش را دارد (تایید شد در `accounts/models.py`): `platform_admin` (فقط تیم مالک/توسعه کاریز)، `sales_manager` (مدیر فروشگاه مشتری)، `sales_agent` (بازاریاب/فروشنده، حساب کاربری جدا برای هرکس، حساب اشتراکی ممنوع)، `company_it` (**غیرفعال به‌صورت پیش‌فرض برای Client 1**؛ یک حساب فنی محدود آینده نیازمند قرارداد تصویب‌شده جداست و هرگز نباید `platform_admin` را اعطا/هدف‌گیری/مدیریت کند). **فقط `platform_admin` مجاز به ساخت، ویرایش، غیرفعال‌سازی، فعال‌سازی مجدد، یا reset رمز کاربران است؛ فقط `platform_admin` مجاز به تغییر نقش یا workstream عملیاتی است. `sales_manager` هیچ قابلیت مدیریت کاربر ندارد** — فقط داده/گزارش عملیاتی کسب‌وکار. این یک تصمیم بسته است، نه یک گزینه مشروط به تصمیم بعدی؛ ببینید بخش ۶ برای شکاف دقیق بین این سیاست و رفتار فعلی کد. Django Admin و مدیریت سرور/دیتابیس هرگز به کاربر مشتری افشا نمی‌شود. احراز هویت فعلی نام‌کاربری/رمز است؛ دسترسی فقط از سیستم‌های کنترل‌شده شرکت در دفتر تهران روی مسیر شبکه خصوصی درنظر گرفته می‌شود.
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

## ۴. هدف کامل موردنیاز Client 1 — سه رده صریح (اصلاح P0R)

**اصلاح:** نسخه قبلی این بخش هر capability نام‌برده در هر سند/prompt را به‌طور یکسان «هدف تاییدشده Client 1» معرفی می‌کرد. این یک گسترش دامنه بدون پشتوانه تصمیم مستقیم بود. جایگزین آن سه رده صریح زیر است که اکنون در `BACKEND_SPEC.md` §2.6 هم به‌طور کامل ثبت شده؛ اینجا فقط خلاصه عملیاتی است.

**رده A — پایه پیاده‌سازی‌شده.** فقط مواردی که با model/migration/service/API/UI نگهداری‌شده/تست واقعی ثابت شده‌اند (جزئیات کامل در بخش ۳ و ۵): احراز هویت/نشست/پروفایل؛ نقش‌های ثابت و object scope؛ کاربران؛ مشتری و شماره تلفن؛ Lead/تخصیص/تاریخچه؛ Interaction/پیگیری؛ ProductCategory/Product؛ Sale عملیاتی؛ SalesDocument و گزارش وضعیت پستی داخلی؛ AfterSalesRequest؛ ذخیره/گزارش داخلی InboundSMS (provider-neutral)؛ داشبورد عملکرد فعلی و XLSX؛ ActivityLog؛ API نسخه‌دار، OpenAPI، health و کنترل‌های امنیتی فعلی.

**رده B — هدف تاییدشده Client 1.** مالک محصول صراحتا این خانواده‌های غایب را اولویت‌دار کرده؛ هرکدام قبل از کد به gate تصمیم/acceptance مخصوص خودش نیاز دارد: انبار و موجودی؛ حرکت انبار؛ بهای تمام‌شده خرید؛ قیمت‌گذاری/تخفیف/سود تاییدشده؛ Order و Quotation (چرخه باید تصویب شود)؛ Invoice/InvoiceItem حسابداری-حقوقی؛ مالیات/شماره‌گذاری/رُند‌کردن/اصلاح/ابطال تاییدشده؛ Payment؛ چک؛ قسط؛ حساب/دفتر مشتری؛ مطالبات؛ گزارش سود/زیان تاییدشده؛ PDF و چاپ عملیاتی (**انتظار می‌رود در اولین تحویل عملیاتی باشد، ولی تا رسیدن معنای دقیق سند و یک نمونه ردشده تاییدشده مسدود می‌ماند** — اولویت آن در Roadmap زودتر از سایر موارد رده B است)؛ فایل/سند عملیاتی امن؛ یکپارچگی‌های تاییدشده وب‌سایت/فروشگاه/پرداخت/حسابداری فقط پس از رسیدن provider دقیق و مستندات رسمی.

**رده C — کاندید یا backlog کم‌اولویت.** تا تصمیم مستقیم تازه، اینها را تحویل تاییدشده Client 1 اعلام نکن: طراح پویای نقش/مجوز؛ Opportunity/Pipeline کامل؛ موتور automation عمومی؛ PWA نصب‌شدنی؛ تشخیص فعالیت غیرعادی؛ مجموعه کامل Task/Project/Meeting؛ جستجوی سراسری بین‌ماژولی؛ فیلتر ذخیره‌شده؛ import گروهی XLSX؛ report builder پویا فراتر از گزارش‌های تاییدشده؛ هر صفحه نمایشی Metronic/vendor؛ هر توسعه آواتار/اعلان/مدیریت نشست؛ هر provider ارتباطی فراتر از پیامک قراردادشده؛ عملکرد دلبخواه دیگر از قالب.

هیچ ماژول جدید فقط به‌خاطر عضویت در رده B implemented اعلام نمی‌شود؛ عضویت رده B یعنی «باید نهایتا تصمیم‌گیری و ساخته شود»، نه «همین حالا مجاز به پیاده‌سازی». یکپارچگی‌های بیرونی (وب‌سایت، درگاه پرداخت، حسابداری، پیامک، ایمیل، تلفنی) تا مستندات رسمی provider + credential + owner برسد `BLOCKED_EXTERNAL` می‌مانند.

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
| ورود/پروفایل خود | بله | بله | بله (اگر فعال شود) | بله |
| مدیریت کاربر (ساخت/ویرایش/غیرفعال/فعال‌سازی/reset رمز/role/workstream) — **اجراشده در کد** | خیر | **خیر** | **خیر** | همه هویت‌های تمیز CRM |
| اعطای نقش | خیر | خیر | **خیر** | بله، هر نقش ثابت |
| Customer/Lead/Interaction | فقط assigned/created خود | همه شرکت | همه شرکت (اگر فعال شود) | همه شرکت |
| Product/Category مدیریت | فقط خواندن (active) | بله | بله (اگر فعال شود) | بله |
| Sale ثبت/لغو | assigned Lead خود / لغو ندارد | ثبت+لغو، audited | ثبت+لغو، audited (اگر فعال شود) | ثبت+لغو، audited |
| After-Sales | فقط اگر workstream=`after_sales`، فقط پرونده تخصیص‌یافته | همه پرونده شرکت | همه پرونده شرکت (اگر فعال شود) | همه پرونده شرکت |
| گزارش عملکرد | فقط خودش | شرکت | شرکت (اگر فعال شود) | شرکت |
| Audit log | خیر | خیر (BIZ-011 باز) | audit غیر-platform؛ غیرفعال پیش‌فرض | audit کامل |
| Django Admin/سرور | خیر | خیر | خیر (پیش‌فرض) | مسیر مدیریت جدا، هرگز به کاربر مشتری افشا نمی‌شود |

این ماتریس ستون‌های Customer/Lead/Product/Sale/After-Sales/گزارش/audit را با enforcement واقعی در `sales/selectors.py`، `aftersales/selectors.py`، `auditlog/selectors.py` تایید می‌کند؛ frontend فقط نمایش است و مرز امنیتی نیست. **ردیف «مدیریت کاربر» تنها ردیفی است که سیاست Client 1 (ستون بالا) با رفتار فعلی کد فرق دارد — بلوک زیر را ببینید.**

**وضعیت (فاز `P1.7`، ۲۰۲۶/۰۸/۱۵): پیاده‌سازی شد — شکاف بسته است.** `users.manage_agents` و `users.manage_non_platform` از `accounts/access.py` حذف شدند، پس `sales_manager`، `company_it` و `sales_agent` هیچ capability از خانواده `users.manage_*` ندارند. در نتیجه `IsUserReader` کل `/api/v1/users/` را برایشان می‌بندد و `common/ui_views.py` هم لینک ناوبری را پنهان و صفحه‌ها را ۴۰۳ می‌کند. `USER_ADMINS` در `accounts/services.py` اکنون `{User.Role.PLATFORM_ADMIN}` است که لایه سرویس را برای **هر** فراخوان (شامل management command) مرجع می‌کند، و `UserViewSet._require_admin` هم با آن هم‌راستا شد. این پیش‌فرض امن کدبیس مشترک است، نه یک شاخه Client-1. پوشش رگرسیون: `accounts/tests/test_user_administration_policy.py`.

## ۷. اصول deployment profile چندمشتری

اصول تصمیم‌شده در بخش ۲ باید در آینده به یک مکانیزم صریح تبدیل شود. **این مکانیزم امروز در کد وجود ندارد** — تنها جداسازی امروز از طریق دیتابیس/تنظیمات جدا در سطح deployment (نه کد) قابل انجام است. جدا از نبود کد، یعنی امروز حتی «غیرفعال به‌صورت پیش‌فرض» بودن `company_it` برای Client 1 (بخش ۲/۶) فقط یک سیاست عملیاتی است (هرگز چنین حسابی نساز/فعال نکن)، نه یک قفل فنی.

```text
PROFILE-001 RESOLVED (2026-08-15)
Selected: Option C
  signed external deployment manifest = source of truth
  verified runtime database cache     = derived state only

پیاده‌سازی هنوز شروع نشده و در P3 انجام می‌شود. قواعد الزامی آن فاز:
  - کلید امضای خصوصی تحت کنترل کاریز می‌ماند و هرگز به مشتری تحویل
    نمی‌شود؛ اپلیکیشن فقط کلید عمومی راستی‌آزمایی را دارد.
  - manifest نامعتبر یا ناشناخته fail-closed است.
  - کش دیتابیس هرگز مرجع نیست؛ restore یک دیتابیس قدیمی نباید manifest
    امضاشده را override کند.
  - feature availability، role permission و object scope سه کنترل جدا
    می‌مانند؛ غیرفعال‌کردن feature داده تاریخی را حذف نمی‌کند.
  - بدون شاخه دائمی مشتری و بدون `if client_name == ...` در کد.
  - در این فاز هیچ expiration، kill-switch از راه دور، فعال‌سازی آنلاین
    دوره‌ای یا خاموشی اجباری اضافه نمی‌شود.
مقایسه کامل ۱۴ معیار: docs/backend/DEPLOYMENT_PROFILE_OPTIONS.md
```

مقایسه دقیق سه گزینه طراحی (manifest امضاشده بیرونی / مدل دیتابیسی / ترکیب manifest+cache) و معیارهای مقایسه در Roadmap ثبت شده؛ اینجا تکرار نمی‌شود تا duplicate-prone نشود.

## ۸. مدل تهدید حفاظت از سورس و تضمین واقع‌بینانه

مالک فیزیکی هاست (مشتری) طبق تصمیم مستقیم ممکن است دسترسی Administrator داشته باشد؛ رازداری مطلق سورس از چنین مالکی تضمین فنی ندارد. وضعیت فعلی واقعی، نه فرضی:

- **یافته: ریسک تاییدشده در سطح تعریف build، نه یک artifact ساخته‌شده و بازرسی‌شده.** `Dockerfile` با `COPY . .` (خط ۱۵) کل build context را کپی می‌کند. `.dockerignore` مسیرهای vendor/demo، `.git`، `.env*` و فایل‌های secret-shaped را exclude می‌کند اما **`docs/**`، فایل‌های ریشه `*.md` (شامل `BACKEND_SPEC.md`، همین `KARIZ_PROJECT_HANDOFF.md`، `KARIZ_CLIENT1_CODEX_ROADMAP.md`)، کل `*/tests/**`، `scripts/**`، `nginx/**`، `compose*.yml`، `requirements-direct.txt` را exclude نمی‌کند.** دقت لازم درباره این یافته (اصلاح P0R):
  - این نتیجه از **بازرسی ایستای تعریف build** (`Dockerfile` + `.dockerignore`) به‌دست آمده — اثبات می‌کند که تعریف فعلی build، محتوای ممنوعه را وارد می‌کند.
  - P0/P0R هیچ ایمیج Docker واقعی build و extract نکردند (Docker روی این هاست نصب نیست، تایید شد در بخش ۱۱)؛ بنابراین این یافته **اثبات نمی‌کند** که هر نشتی ممکن دیگر هم فهرست شده — فقط همین gap مشخص در همین دو فایل تایید شده است.
  - سخت‌سازی `.dockerignore` به‌تنهایی منطق کسب‌وکار پایتون خوانا را پنهان نمی‌کند؛ حتی با `.dockerignore` کامل، سورس `.py` غیر-compiled همچنان در ایمیج باقی می‌ماند و برای هرکس با دسترسی به ایمیج/هاست قابل خواندن است.
  - کامپایل/بسته‌بندی backend (تا حدی که readable Python source شیپ نشود) یک فاز feasibility جداست (Roadmap P12)، نه یک تغییر کوچک کنار `.dockerignore`.
- این نشتی توسط هیچ gate موجود پوشش داده نمی‌شود: `docs/ops/SECURITY_SCANS.md` فقط secret (Gitleaks)، آسیب‌پذیری بسته (pip-audit/Grype/SBOM) و TLS خارجی را چک می‌کند، نه محتوای فایل ایمیج. `docs/ops/RELEASE_CHECKLIST.md` فقط diff مخزن Git را review می‌کند، نه محتوای ایمیج ساخته‌شده. `docs/ops/SOURCE_MANIFEST.md` فقط تغییرات commit به commit را classify می‌کند، نه خروجی `docker build`. این یک gap مستندنشده است، نه ریسک شناخته‌شده قبلی.
- نکته مثبت تاییدشده: خود `compose.yml`/`compose.restore-verify.yml`/`compose.write-stop.yml` هیچ `build:` context ندارند (فقط `image: repo@sha256:digest` pull می‌کنند)؛ هیچ پورت PostgreSQL یا اپ مستقیما به هاست/شبکه عمومی publish نمی‌شود (فقط Nginx 80/443)؛ `restore-verify` با `network_mode: none` اجرا می‌شود. نشتی فقط در لحظه build ایمیج رخ می‌دهد، نه در هر بار اجرای Compose.
- هدف واقع‌بینانه طبق تصمیم مالک محصول: نبود repo/toolchain/تست/مستندات توسعه در تحویل، backend کامپایل/بسته‌بندی‌شده در جایی که عملی است، فرانت بدون source map، بدون کلید امضا روی هاست مشتری، بروزرسانی/rollback فقط از مسیر مالک پلتفرم. **هیچ‌کدام از این‌ها امروز پیاده نشده؛ فقط feasibility ممیزی و gate برنامه‌ریزی شد (طبق دستور صریح P0، هیچ packaging/license enforcement در این فاز اجرا نشد).**
- برندینگ/نام مشتری: تمیز. `metronic`/`keenthemes` فقط در دو assertion منفی تست (`common/tests/test_ui.py`) و در اسناد/ابزار داخلی (`scripts/check_html_branding.py`، `docs/codebase/BRANDING_CLEANUP.md`) دیده می‌شود، هرگز در خروجی served. «Client-1» فقط به‌عنوان کد داخلی پروژه در اسناد دیده می‌شود، هرگز در template/fixture/API response/نام بسته served. نام شخص‌ثالث واقعی («Satras Web»، یک theme localizer قدیمی) فقط داخل درخت vendor exclude‌شده و در regex ابزار حذف‌کننده دیده شد. هیچ source map در `common/static/common/**` نیست.

## ۹. نقص‌ها و ریسک‌های P0/P1 فعلی

| # | نقص | شدت | محل | اقدام |
|---|---|---|---|---|
| 1 | نشتی محتوای ایمیج Docker (بخش ۸) | **P0 — برطرف شد در سطح تعریف build** | `.dockerignore` | **در فاز P0R.4 اصلاح شد.** ۴۰۸ → ۱۴۷ فایل، ۱۴۲ → ۰ مورد ممنوعه (بخش ۰). گیت رگرسیون: `common/tests/test_image_content.py`. باقی‌مانده: اجرای `python scripts/validate_image_content.py --listing` روی یک ایمیج واقعی روی هاست دارای Docker. |
| 1ب | الگوهای `__pycache__`/`*.pyc`/`*.log` در `.dockerignore` root-anchored بودند و bytecode توسعه‌دهنده وارد ایمیج می‌شد | P1 — برطرف شد | `.dockerignore` | فرم‌های `**/` اضافه شدند (بخش ۰). |
| 2 | تناقض داخلی `BACKEND_SPEC.md` بخش ۲.۳/۲.۴ (وضعیت پستی و گزارش پیامک ورودی را «blocked» می‌گفت درحالی‌که در همان سند بخش ۵.۷A/۵.۹ و در کد واقعی پیاده شده‌اند) | P1 مستندات | `BACKEND_SPEC.md` | در همین فاز اصلاح شد (بخش زیر). |
| 3 | خطای HTML: `sales_documents/detail.html:16` — attribute `maxlength="500` بدون quote بسته؛ پاراگراف خطای فیلد «reason» در DOM ساخته نمی‌شد و پیام خطای سرور به کاربر نشان داده نمی‌شد | P1 — **برطرف شد در `P2` (۲۰۲۶/۰۸/۱۵)** | همان فایل | یک کوتیشن بسته اضافه شد. پوشش رگرسیون در سطح DOM و مرورگر واقعی، هر دو تاییدشده با اجرای پیش از اصلاح. ادعای قبلی درباره از کار افتادن `maxlength` با اندازه‌گیری در Chrome رد شد — بخش ۰. |
| 4 | `docs/KARIZ_CAPABILITIES_FOR_INVOICE_FA.txt` (پیوست فاکتور مشتری، تاریخ ۲۰۲۶/۰۸/۱۰) نسبت به قابلیت‌های تکمیل‌شده بعدی (ProductCategory، گزارش پیامک ورودی، پنل خدمات پس از فروش) بروز نیست | P2 اسنادی | همان فایل | باید پیش از استفاده تجاری بعدی بازبینی شود؛ در این فاز تغییر نکرد چون سند دو-فایل زنده مصوب (Handoff/Roadmap) نیست. |
| 6 | Django Admin بدون گیت تنظیمات ثبت شده بود و در شبکه قابل دسترسی بود | **MEDIUM — برطرف شد در `P1.7`** | `config/settings.py`, `config/production_settings.py`, `config/urls.py`, `nginx/default.conf` | **دو لایه دفاعی مستقل اضافه شد.** لایه اپلیکیشن: تنظیم جدید `ENABLE_DJANGO_ADMIN` که پیش‌فرض `false` است و **مستقل از `DEBUG`** عمل می‌کند؛ در `production_settings.py` صریحا `False` است؛ مسیر `admin/` فقط وقتی ثبت می‌شود که این پرچم روشن باشد، پس روی استقرار مشتری `/admin/` اصلا وجود ندارد (۴۰۴). لایه edge: بلوک `location ^~ /admin/ { return 404; }` در `nginx/default.conf` که به‌خاطر `^~` بر همه location‌های regex اولویت دارد و هیچ درخواستی را proxy نمی‌کند. تست: `common/tests/test_admin_exposure.py` (۱۳ تست). allowlist شبکه مدیریت عمدا حدس زده نشد و به `P14` موکول شد. |
| 7 | عملگر after-sales روی `customers`/`leads`/`sales` پاسخ `200` با صفر ردیف می‌گیرد، درحالی‌که `users`/`activity-logs`/`inbound-sms` برای بازاریاب `403` می‌دهند | LOW (ناسازگاری، نه نشت — مرز داده برقرار است و direct-ID = 404) | selector/permission لایه sales | یکسان‌سازی به `403` برای نبود capability. اختیاری، در `P1.7` یا `P2`. |
| 5 | عدم‌تطابق نسخه Python: هاست توسعه فعلی `Python 3.14.5` دارد؛ `Dockerfile` فقط base image با `sys.version_info[:2] == (3, 13)` را می‌پذیرد | اطلاع‌رسانی، نه نقص | `Dockerfile:12` | تست‌های محلی روی 3.14.5 pass شدند ولی رفتار دقیق production روی 3.13 محلی proof نشده؛ در build واقعی هدف تایید شود. |

## ۱۰. blockerهای بیرونی deployment (ورودی گزارش‌شده، نه fact اثبات‌شده)

- هاست گزارش‌شده «Windows Server 2008» در پرند؛ ۱۶ گیگ RAM، حدود ۲ ترابایت SSD؛ نرم‌افزار حسابداری و حداقل یک اپ دیگر روی همان هاست. **تا شواهد دقیق `winver`/`systeminfo`، Windows Server 2008/2008 R2 هدف تولید پشتیبانی‌شده تلقی نمی‌شود** و مستقیما روی آن طراحی/ادعای استقرار نمی‌شود.
- تهران و پرند ادعای IP عمومی ثابت دارند؛ مدل روتر، UPS، آنتی‌ویروس/EDR، مقصد backup، مالک restore، RPO/RTO، peak concurrency، پنجره نگهداری نامشخص‌اند.
- بدون domain/DNS عمومی تاییدشده. دسترسی بازاریاب‌ها فعلا فقط از سیستم ثابت دفتر تهران لازم است.
- هدف شبکه ترجیحی: VPN سایت-به-سایت روتر-به-روتر با HTTPS روی تونل خصوصی برای کاربران ثابت تهران؛ VPN فردی فقط برای مدیریت یا کاربران واقعا خارج از دفتر. PostgreSQL، پورت اپ، Django Admin، SSH، RDP، مدیریت کانتینر و backup service علنی نمی‌شوند (این محدودیت آخر با تنظیمات فعلی Compose تایید شد — بخش ۸).
- این‌ها همگی `BLOCKED_EXTERNAL` هستند؛ سوالات دقیق در بخش ۱۴.

## ۱۱. دستورهای دقیق و شواهد فعلی

بخش الف — اجراشده در فاز P0 (شواهد پایه، همچنان معتبر چون هیچ کد اپلیکیشنی از آن زمان تغییر نکرده):

```text
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
which docker / which psql (bash)     → یافت نشد
```

بخش ب — دوباره اجراشده در فاز P0R (بعد از commit مستقل `AGENTS.md`، همین هاست):

```text
git rev-parse --show-toplevel        → C:/Users/Dear-OTCamp-User/Desktop/Kariz-CRM
git branch --show-current            → main
git rev-parse HEAD                   → 122b4707bbdd92c095fe85917cdb4ed72c66083d
git status --short (قبل از ویرایش‌های P0R) → خالی
git status --short (حین ویرایش‌های P0R)   → " M BACKEND_SPEC.md" و " M KARIZ_PROJECT_HANDOFF.md" (unstaged، طبق دستور)
git diff --check                     → exit 0 (فقط هشدار تبدیل خط CRLF/LF گیت، نه خطای whitespace واقعی)
python manage.py check --settings=config.test_settings
    → "System check identified no issues (0 silenced)."
python manage.py makemigrations --check --dry-run --settings=config.test_settings
    → "No changes detected"
```

هیچ کد اپلیکیشنی در P0R تغییر نکرد، بنابراین اجرای مجدد کل test suite لازم نبود و انجام نشد (طبق دستور صریح این فاز). هیچ نتیجه بالا جایگزین شواهد اجراشده روی محیط هدف واقعی نمی‌شود.

## ۱۲. وضعیت انتشار فعلی

`production candidate; external verification pending` — بدون تغییر نسبت به قبل، اکنون با شواهد تازه‌تر: مخزن/تست/schema/branding محلی سبز است (بخش ۱۱)، اما ایمیج immutable واقعی، PostgreSQL/Compose/Nginx زنده، TLS واقعی، backup/restore واقعی، load/scan هدف، UAT هدف و rollback drill انجام نشده و روی این هاست ابزارش موجود نیست. `NO-GO` برای هرگونه استقرار تا این فاز باقی می‌ماند. تا زمانی که یافته P0 بخش ۹ ردیف ۱ (نشتی محتوای ایمیج) اصلاح و بازبینی نشود، حتی تولید یک ایمیج «آماده انتشار» هم نباید انجام شود.

## ۱۳. فاز دقیق بعدی و اقدام دقیق ازسرگیری

فاز بعدی `P1 — بستن تصمیم‌های کسب‌وکار/دامنه باز` طبق `KARIZ_CLIENT1_CODEX_ROADMAP.md` است، مشروط به پاسخ مالک محصول به سوالات بخش ۱۴. موازی و مستقل از آن: `P0R.1` (survey زودهنگام زیرساخت) و `P0R.2` (راه‌اندازی PostgreSQL محلی/staging) می‌توانند بدون انتظار برای تصمیم‌های مالی شروع شوند؛ `P2` (رفع نقص کوچک HTML بخش ۹ ردیف ۳) نیز مستقل قابل شروع است. اقدام دقیق ازسرگیری: مالک محصول به سوالات شماره‌گذاری‌شده در بخش ۱۴ پاسخ دهد و یکی از گزینه‌های طراحی deployment-profile (Option A/B/C در Roadmap) را انتخاب کند؛ سپس با هر تصمیم مصوب، `KARIZ_CLIENT1_CODEX_ROADMAP.md` فاز مربوطه به‌روزرسانی و پیاده‌سازی محدود همان تصمیم آغاز شود. اصلاح نشتی تعریف build ایمیج (بخش ۹ ردیف ۱) باید پیش از هر تلاش build ایمیج واقعی انجام شود، مستقل از تصمیم‌های کسب‌وکار. این diff فعلی (P0R) بدون commit در working tree باقی می‌ماند تا بازبینی انسانی انجام شود.

## ۱۴. شناسه‌های تصمیم باز (شماره‌گذاری‌شده)

مصوب و بسته (فقط برای provenance، دیگر باز نیستند): نگاشت نقش‌ها/برچسب فارسی؛ نبود مدل Team برای Client 1؛ جداسازی workstream `sales`/`after_sales`؛ **`BIZ-005` (۲۰۲۶/۰۸/۱۴) — Sales Manager هیچ قابلیت مدیریت کاربر ندارد؛ `company_it` غیرفعال پیش‌فرض برای Client 1** (بخش ۲/۶؛ شکاف پیاده‌سازی مربوطه باز است، نه خودِ تصمیم).

```text
DOC-001 RESOLVED
AGENTS.md قدیمی (۲۷۲ خط) بازگردانده نمی‌شود. یک CLAUDE.md مختصر ریشه
(حداکثر ~۱۲۰ خط) جایگزین آن برای قوانین پایدار مخزن است. این فاز آن را
ایجاد کرد (بدون stage). دلیل: AGENTS.md قدیمی بسیار محدودکننده و
checkpoint-محور بود؛ CLAUDE.md فقط قوانین پایدار را نگه می‌دارد و مانع
بازرسی کد first-party مرتبط نمی‌شود.

PROFILE-001 PARTIALLY RESOLVED
به بخش ۷ نگاه کنید. Architecture discovery تایید شده؛ پیاده‌سازی تا
انتخاب یکی از Option A/B/C تایید نشده.
```

باز — کسب‌وکار/دامنه:

1. `BIZ-001` روش تخصیص اولیه Lead.
2. `BIZ-002` فهرست نهایی وضعیت و گذار Lead.
3. `BIZ-003` گروه‌بندی outcome تماس واجد شرایط.
4. `BIZ-004` معنای دقیق KPI مشتری/نرخ تبدیل.
5. `BIZ-006` معنای دقیق correction فروش (فراتر از cancel فعلی).
6. `BIZ-007` برچسب/قالب/تقویم جلالی خروجی XLSX.
7. `BIZ-008` گراف وضعیت/reopen/SLA خدمات پس از فروش.
8. `BIZ-009` زمان‌بندی/نگهداری/مالک/RPO/RTO backup.
9. `BIZ-010` هدف ظرفیت/بار همزمان و قانون abort.
10. `BIZ-011` مرز audit قابل‌مشاهده برای Sales Manager.
11. `BIZ-012` سیاست backfill یا رد دائمی رکوردهای audit قدیمی.
12. `BIZ-013` رفتار Lead فعال هنگام غیرفعال‌سازی کاربر مالک آن.

باز — دامنه‌های بزرگ (هرکدام باید قبل از کد شروع شود؛ ترتیب اولویت اجرا در Roadmap P5-P8). **پرسش‌های دقیق و پاسخ‌پذیر هر خانواده در `docs/backend/OPEN_BUSINESS_DECISIONS.md` باز شده‌اند؛ همین بخش رجیستر معتبر است و آن سند تابع آن.** پاسخ جزئی هم مفید است: هر خانواده که کامل پاسخ بگیرد، فاز خودش را فورا آزاد می‌کند.

13. Inventory/انبار: واحد، مکان انبار، موجودی اول دوره، رزرو، منفی‌شدن، اصلاح/برگشت.
14. Order و Quotation: چرخه، منبع، تبدیل، شماره‌گذاری، تاییدها (نمونه‌های چرخه ممکن، نه تصویب‌شده، در Roadmap §۷.۴).
15. Invoice/InvoiceItem حسابداری-حقوقی: منبع دقیق (مستقیم از مشتری، فقط از Sale، فقط از Order/Quotation، یا چند مسیر)، حوزه مالیاتی، نرخ، ترتیب تخفیف، رُند کردن، شماره‌گذاری، اصلاح/ابطال، snapshot. **نمونه فاکتور/PDF ردشده (redacted) اولویت بالاتری از بقیه موارد رده B دارد چون PDF برای اولین تحویل عملیاتی انتظار می‌رود (بخش ۴).**
16. Payment، چک، قسط: روش‌ها، آیا تخصیص به Invoice اجباری است یا پرداخت روی حساب بدون تخصیص فوری هم مجاز است، idempotency، reversal/refund، تطبیق.
17. حساب/دفتر مشتری (Customer Ledger): قرارداد بدهکار/بستانکار، موجودی اول دوره، تعدیل.
18. مطالبات و سود/زیان: مبنای حسابداری (نقدی/تعهدی)، فرمول دقیق، منبع هزینه/موجودی، دوره بستن.
19. فایل/سند عملیاتی: نوع/حجم مجاز، نگهداری، دانلود، malware scan.
20. یکپارچگی‌های بیرونی (وب‌سایت/فروشگاه/درگاه/حسابداری/ایمیل/پیامک/تلفنی): provider دقیق، مستندات رسمی، credential، owner، retry/reconciliation.

باز — استقرار/زیرساخت (پاسخ مالک محصول یا صاحب زیرساخت لازم است؛ Roadmap این‌ها را زودتر، موازی با P1، قرار می‌دهد):

21. شواهد دقیق `winver` و `systeminfo` هاست پرند؛ آیا «Windows Server 2008» نسخه OS است یا SQL Server یا نرم‌افزار حسابداری؟
22. ادیشن Windows، Service Pack، معماری، ظرفیت مجازی‌سازی.
23. مدل/برند/firmware روتر تهران و پرند.
24. دامنه Active Directory در برابر دامنه اینترنتی عمومی؛ مالکیت DNS.
25. تصمیم مصوب: سرور/appliance اختصاصی پشتیبانی‌شده یا ارتقای OS پشتیبانی‌شده؟
26. تعداد کل و peak همزمان کاربران مورد انتظار.
27. وضعیت UPS و endpoint security/antivirus.
28. مقصد backup خارج از سایت و مقصد همیشه-روشن تهران؛ مالک نگهداری/بازیابی/حادثه؛ پنجره نگهداری.
29. تایید نهایی حفاظت سورس/امضای release و سیاست تجاری پشتیبانی/بروزرسانی.

باز — معماری (تولید همین فاز):

30. کدام گزینه طراحی deployment-profile تایید می‌شود — Option A (manifest امضاشده بیرونی)، Option B (مدل دیتابیسی `DeploymentProfile`)، یا Option C (ترکیب manifest + کش رانتایم دیتابیس)؟ **مقایسه کامل روی هر ۱۴ معیار اکنون در `docs/backend/DEPLOYMENT_PROFILE_OPTIONS.md` آماده است.** ارزیابی مهندسی: Option C توصیه می‌شود، Option A جایگزین کوچک‌تر قابل‌قبول، Option B توصیه نمی‌شود (کنترل entitlement داخل ذخیره‌ای که مشتری می‌تواند ویرایش کند، و restore از backup قدیمی می‌تواند feature حذف‌شده را بی‌صدا برگرداند). انتخاب نهایی با مالک محصول است.
31. **(مسدودکننده فعال `P0R.2`)** کدام مسیر برای فراهم‌کردن PostgreSQL 17 تایید می‌شود؟ گزینه‌ها به‌ترتیب کم‌اثرترین: **(الف)** استخراج آرشیو باینری ویندوز در یک پوشه و اجرای `scripts/test-postgres.ps1 -PostgresBin '<path>\bin'` — بدون نصب، بدون سرویس، بدون registry، بدون دسترسی administrator؛ **(ب)** نصب معمولی PostgreSQL 17؛ **(ج)** یک VM توسعه یک‌بارمصرف. هیچ‌کدام بدون اجازه صریح شما انجام نمی‌شود. ضمنا برای نیمه «restore» این فاز، یا Docker لازم است یا افزودن یک گام restore native به harness — تایید کنید کدام (بخش ۰.۰).
