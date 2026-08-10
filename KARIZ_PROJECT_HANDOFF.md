# Kariz CRM project handoff

این فایل تنها سند وضعیت جاری پروژه است. وضعیت اجراشده، تصمیم‌های ثابت، کارهای مانده، blockerها و فرمان ادامه در همین فایل نگهداری می‌شود.

## 1. وضعیت نهایی فعلی

- وضعیت: `production candidate; external verification pending`.
- سطح تکمیل: State B. همه کارهای قابل انجام داخل repository تمام شده است.
- production ready واقعی هنوز ادعا نمی‌شود؛ Phase 12 به ابزار، میزبان و تصمیم‌های بیرونی نیاز دارد.
- آخرین source ref تاییدشده: `95dbc71ea3a3e773a620271f3d3fbe0e88646e8b`.
- `HEAD` و `origin/main` هنگام proof برابر بودند.
- delta از baseline `50a978abc206e43032ce96b36dc0433366198e60`: 134 مسیر؛ 47 تغییر، 87 فایل جدید، بدون حذف یا rename.
- پاک‌سازی و ادغام اسناد روت بعد از آن ref انجام شده و تا review/commit کاربر یک documentation-only worktree change است.
- ممیزی backend و operations هر دو امتیاز 9/10 گرفتند. P0/P1 تاییدشده داخل repository باقی نماند.
- فایل‌های status قدیمی روت در این فایل ادغام شدند. تاریخ کامل آن‌ها در Git باقی است.

## 2. منابعی که هنوز معتبر و جدا هستند

- `AGENTS.md`: قواعد کار و ایمنی repository.
- `BACKEND_SPEC.md`: قرارداد موقت ولی authoritative محصول و backend.
- `docs/backend/ENTITY_CATALOG.md`: تعریف entityها.
- `docs/backend/RELATIONSHIPS.md`: رابطه‌ها.
- `docs/backend/ERD.mmd`: ERD.
- `docs/backend/API_CONTRACT.md`: قرارداد HTTP/API.
- `docs/backend/DISCOVERY.md`: مرز source و runtime.
- `docs/ops/`: runbookهای deploy، TLS، backup، restore، rollback، incident، UAT، load و scan.

این فایل جایگزین سندهای روت `ASSUMPTIONS.md`، `BLOCKERS.md`, `CODEBASE_MAP.md`, `FILE_REVIEW_LEDGER.md`, `PRODUCTION_READINESS_CHECKLIST.md`, `PROJECT_ROADMAP.md`, `WORKLOG.md`, هدف اجرای قدیمی و patch اجرای قدیمی شده است.

## 3. چیزهایی که انجام شد

| بخش | نتیجه |
|---|---|
| Repository safety | ignoreها، secret/path gate، baseline و release ref ثبت شد |
| Codebase map | 179 فایل first-party بررسی و ماژول‌ها/entry pointها ثبت شد |
| Schema | User، Customer، Phone، Lead، history، Interaction، Product، Sale و ActivityLog guard شدند |
| Authentication | Django Session + CSRF، inactive denial، password validation و server-field rejection کامل شد |
| Authorization | چهار role ثابت و object/query scope fail-closed شد |
| Server identity | staff، superuser، group و direct permission از CRM جدا شد |
| Audit | request ID، role snapshot، safe log و read scope برای Company IT/Platform Admin ساخته شد |
| API | `/api/v1/`، JSON-only، stable error envelope، 406/415/409/413/429/500 و OpenAPI کامل شد |
| Sales workflows | assignment/reassignment، interaction append-only، sale create/cancel و audit service-based شد |
| Reports | JSON و XLSX با scope یکسان، money دقیق، filter امن و formula defense ساخته شد |
| Persian UI | `/` و admin فارسی/RTL و Kariz branded شد |
| Production config | secure settings، digest refs، read-only web، health، TLS edge و write-stop اضافه شد |
| Database roles | init، migration، app و backup login جدا و ACL محدود شد |
| Recovery | backup، checksum، retention guard، no-network restore verifier و rollback runbook ساخته شد |
| Reliability | body/depth/text bounds، throttling، query-growth tests و PostgreSQL harness اضافه شد |
| Supply gate | hash-locked Python packages، image ref validator، SBOM/scan runbook اضافه شد |

## 4. معماری و entry pointها

- Django + Django REST Framework + PostgreSQL.
- Modular monolith.
- Single-tenant؛ database جدا برای هر شرکت.
- Same-origin Session Authentication + CSRF.
- API base: `/api/v1/`.
- UI فعال: `/` و Django admin.
- health:
  - `/api/v1/health/live/`
  - `/api/v1/health/ready/`
- docs/schema در production خاموش است.
- ماژول‌ها:
  - `accounts/`: identity، role، login، user admin، bootstrap و UAT seed.
  - `sales/`: Customer، Phone، Lead، Interaction، Product و Sale.
  - `auditlog/`: append-oriented ActivityLog و read scope.
  - `reports/`: user-performance JSON/XLSX.
  - `common/`: error، middleware، request context/log، throttle، UI و health.
  - `config/`: settings، URL، production/test/PostgreSQL guards.
  - `scripts/`: PostgreSQL proof، backup/restore، load و image validation.
  - `nginx/`: TLS، proxy، rate limit، static و write-stop.

## 5. داده و migrationها

Migration headها:

- `accounts.0002_user_role_constraint`
- `auditlog.0002_activitylog_role_snapshots`
- `sales.0010_interaction_contract`

Guardهای مهم:

- role فقط `sales_agent`, `sales_manager`, `company_it`, `platform_admin`.
- Lead assignment fields به شکل all-or-none.
- active normalized phone در کل سیستم unique.
- phone canonical: `+98` و ده رقم ASCII.
- Product price بزرگ‌تر از صفر.
- Sale quantity، status، snapshot، total و money guard.
- Interaction direction فقط `inbound` یا `outbound`.
- Interaction outcome خالی نیست؛ code set نهایی هنوز تصمیم نشده.
- address حداکثر 2000 و notes/description حداکثر 4000 کاراکتر.
- migrationهای data-sensitive قبل از apply، داده ناسازگار را fail-closed گزارش می‌کنند و چیزی را خودکار پاک یا merge نمی‌کنند.

## 6. API و authorization

Routeهای اصلی:

- `/api/v1/auth/login/`, `/logout/`, `/me/`
- `/api/v1/users/` و change-role
- `/api/v1/customers/`
- `/api/v1/customer-phones/`
- `/api/v1/leads/` و reassign
- `/api/v1/interactions/`
- `/api/v1/products/`
- `/api/v1/sales/` و cancel
- `/api/v1/activity-logs/`
- `/api/v1/reports/user-performance/`
- `/api/v1/exports/user-performance.xlsx`

Role wall:

- Sales Agent فقط scope خود/Leadهای مجاز.
- Sales Manager فقط scope تاییدشده؛ user administration و audit گسترده تا تصویب Team/Audit rule بسته است.
- Company IT عملیات تاییدشده دارد، ولی Platform Admin identity/audit را نمی‌بیند.
- Platform Admin بالاترین CRM role است، ولی Django staff/superuser نیست.
- آخرین active Platform Admin قابل deactivate/demote نیست.
- server-managed identity از list، detail، write، assignment و report پنهان است.
- hidden object و missing object پاسخ هم‌شکل می‌دهند.
- hard delete عادی برای business history وجود ندارد.

## 7. Report و XLSX

Metricهای تاییدشده:

- `customers_created_count`
- `sales_count`
- `sales_amount`
- `average_sale_amount`

قواعد:

- date range نیمه‌باز؛ start شامل و end خارج.
- Agent فقط خود؛ roleهای مجاز scope شرکت.
- Product filter فقط Sale metric را تغییر می‌دهد.
- cancelled Sale حساب نمی‌شود.
- average با `ROUND_HALF_UP` تا `0.01`.
- zero denominator برابر `0.00`.
- JSON و XLSX از یک result استفاده می‌کنند.
- XLSX formula prefix دفاع دارد.
- label/style/Jalali نهایی هنوز تصمیم کسب‌وکار است.

## 8. امنیت و عملیات

- request body: حداکثر 64 KiB.
- JSON container depth: حداکثر 32.
- login throttle: 10 درخواست در دقیقه.
- sensitive user/action/report/audit throttle: 30 درخواست در دقیقه.
- production فعلی برای یک web container با سه Gunicorn worker طراحی شده است.
- horizontal scale نیاز به shared throttle store تاییدشده دارد.
- request log فقط event/request_id/method/path/status/duration دارد.
- query، body، header، IP و secret در application request log نیست.
- Nginx فقط یک proxy hop را trust می‌کند و forwarding header را overwrite می‌کند.
- web filesystem read-only و `/tmp` تنها writable runtime path است.
- production image refs باید digest-qualified باشند.
- PostgreSQL app role owner نیست و audit/history tableها update/delete grant ندارند.
- backup role read-only است.
- write-stop، POST/PUT/PATCH/DELETE را با 503 می‌بندد و read/health را باز نگه می‌دارد.

## 9. تست و proof انجام‌شده

- full suite: 232 تست پاس.
- 6 تست PostgreSQL-only روی SQLite عمدا skip شد.
- `python manage.py check --settings=config.test_settings`: پاس.
- migration drift: صفر.
- OpenAPI validate + fail-on-warn: پاس.
- collectstatic dry run: پاس.
- `pip check`: پاس.
- four-image reference validator: پاس با مقدار تستی.
- Bash syntax: پاس.
- PowerShell parser: پاس.
- production deploy check: پاس؛ فقط HSTS subdomain/preload warningهای عمدی باقی بود.
- manifest و ledger parser: پاس.
- forbidden path: صفر.
- high-confidence secret match: صفر.

ابزارهای زیر هنگام proof روی host موجود نبودند:

- Docker
- Nginx
- `initdb`, `pg_ctl`, `psql`, `pg_dump`, `pg_restore`, `createdb`, `dropdb`

پس proof زنده ادعا نشده است.

## 10. فرض‌های ثابت

- PostgreSQL source of truth است. SQLite فقط fast test است.
- deployment single-tenant است.
- API normal فقط JSON است؛ XLSX تنها binary response تاییدشده است.
- Persian/RTL تنها UI فعال است.
- archive بزرگ static از Django template/image خارج است و حذف نشد؛ مصرف‌کننده بیرونی آن معلوم نیست.
- legacy audit role snapshot خالی می‌ماند؛ Company IT آن را نمی‌بیند و Platform Admin می‌بیند.
- active phone identity global unique است تا workflow دیگری تصویب شود.
- current XLSX machine-readable foundation است، نه قرارداد presentation نهایی.
- existing-data deploy باید قبل از تغییر recovery point سازگار بسازد و restore-check کند.
- هیچ secret، production data یا volume در proof محلی خوانده یا تغییر داده نشد.

## 11. کارهای مانده کسب‌وکار

| ID | تصمیم لازم | رفتار امن فعلی |
|---|---|---|
| BIZ-001 | روش initial Lead assignment | assignment خودکار ساخته نشده |
| BIZ-002 | statusها و transitionهای Lead | transition حدسی وجود ندارد |
| BIZ-003 | outcome code و qualifying-call group | direction ثابت؛ outcome متن bounded |
| BIZ-004 | KPI customer/conversion/reassignment | metric مبهم منتشر نمی‌شود |
| BIZ-005 | Team model و Manager boundary | Manager user admin بسته است |
| BIZ-006 | Sale correction semantics | correction رد؛ cancel موجود |
| BIZ-007 | XLSX labels/style/Jalali | export دقیق machine-readable موجود |
| BIZ-008 | After-sales scope | entity/API ساخته نشده |
| BIZ-009 | backup schedule/retention/owner/RTO/RPO | ابزار guard شده؛ policy زنده ندارد |
| BIZ-010 | capacity/load target و abort rule | harness فقط آماده است |
| BIZ-011 | Manager audit boundary | Manager audit بسته است |
| BIZ-012 | legacy audit backfill یا denial دائمی | Company IT legacy unknown را نمی‌بیند |
| BIZ-013 | deactivate user با Lead فعال | assignee/history خودکار جابه‌جا نمی‌شود |

هر تصمیم باید مکتوب شود و همراه service/API/audit/test مربوط اجرا شود.

## 12. blockerهای بیرونی

| ID | ورودی لازم | proof بسته‌شدن |
|---|---|---|
| EXT-001 | PostgreSQL bin سازگار + Bash | اجرای `scripts/test-postgres.ps1` |
| EXT-002 | Docker + image digests + volume names | Compose pull/boot/health/static/API/write-stop |
| EXT-003 | Nginx runtime | config و HTTP edge proof |
| EXT-004 | hostname + cert/key path + renewal owner | TLS/redirect/HSTS/scanner proof |
| EXT-005 | runtime و backup واقعی | dump + no-network disposable restore |
| EXT-006 | browser و edge UI | desktop/mobile Persian/RTL/brand/console proof |
| EXT-007 | runtime/scanner digests + isolated scan host | SBOM، vuln، dependency، source و TLS evidence |

## 13. ورودی‌های عملیاتی مانده

- OPS-001: current/prior runtime artifacts، محل امن و compatibility owner.
- OPS-002: release/database/security/business/rollback owner و window/abort rule.
- OPS-003: backup scheduler، overlap/timeout، alert، off-host copy، RTO/RPO.
- OPS-004: log retention/access/deletion/alert policy.
- OPS-005: active Platform Admin confirmation یا first-install bootstrap approval.
- OPS-006: write-stop/rollback/incident/cutover/reopen owner و tabletop.

## 14. فرمان دقیق ادامه

اول PostgreSQL proof روی cluster disposable و بدون production data:

```powershell
$approvedPostgresBin = Read-Host 'Approved PostgreSQL bin path'
$approvedBash = Read-Host 'Approved Bash executable path'
.\scripts\test-postgres.ps1 -PostgresBin $approvedPostgresBin -BashCommand $approvedBash
```

بعد، فقط با `.env` محافظت‌شده، digestها و volumeهای تاییدشده:

```powershell
docker compose config --quiet
docker compose -f compose.yml -f compose.write-stop.yml config --quiet
docker compose -f compose.restore-verify.yml --profile restore-verify config --quiet
python scripts/validate_release_images.py
```

سپس ترتیب recovery-first در `docs/ops/DEPLOYMENT.md` اجرا شود. برای backup/restore از `docs/ops/BACKUP_RESTORE.md`، برای TLS از `docs/ops/TLS.md`، برای load از `docs/ops/LOAD_TEST.md` و برای scan از `docs/ops/SECURITY_SCANS.md` استفاده شود.

## 15. قانون ادامه و توقف

- بعد از هر تغییر source، full repository gates و manifest باید تازه شود.
- business rule حدس زده نشود.
- secret در chat، Git، log یا evidence ذخیره نشود.
- روی live data تست destructive اجرا نشود.
- volume حذف یا reset نشود.
- claim مجاز تا بسته‌شدن Phase 12 فقط `production candidate; external verification pending` است.

## 16. پاک‌سازی اسناد روت

اسناد زیر پس از ادغام حذف شدند:

- `AGENTS_KARIZ_CONTINUOUS_EXECUTION_PATCH.md`: محتوای لازم قبلا در `AGENTS.md` ادغام شده بود.
- فایل هدف اجرای قدیمی: هدف به State B رسید؛ وضعیت و gateها اینجا ثبت شد.
- `ASSUMPTIONS.md`
- `BLOCKERS.md`
- `CODEBASE_MAP.md`
- `FILE_REVIEW_LEDGER.md`
- `PRODUCTION_READINESS_CHECKLIST.md`
- `PROJECT_ROADMAP.md`
- `WORKLOG.md`

فایل‌های runtime، specification، deployment، dependency، HTML archive و ابزارهای کاربر حذف نشدند. Git baseline راه بازیابی اسناد حذف‌شده را نگه می‌دارد.
