{% comment %} چارچوب یکپارچه‌سازی (۲.۲۱.۰): اتصال‌های پیکربندی‌شده، وب‌هوک‌های خروجی،
   توکن‌های API و گزارش رویدادها. فقط برای مدیر پلتفرم و فقط وقتی ویژگی‌اش روشن
   است؛ هر API پشت این بخش‌ها همین دو را دوباره بررسی می‌کند. فرم هر نوع اتصال از
   فهرست فیلدهای خود ارائه‌دهنده ساخته می‌شود (`integrations/providers`). رمزها فقط
   نوشتنی‌اند: هرگز از سرور خوانده نمی‌شوند، فقط چند نویسهٔ آخرشان دیده می‌شود. {% endcomment %}
{{ integration_catalog|json_script:"integration-catalog" }}
{% if not integration_secrets_available %}
<div class="alert alert-warning d-flex flex-column p-5 mt-8 mb-0" role="alert">
    <span class="fw-bold mb-1">کلید رمزنگاری تنظیم نشده است</span>
    <span class="fs-7">تا وقتی <code dir="ltr">DOLPHIN_SECRETS_KEY</code> روی این استقرار تنظیم نشده، هیچ رمز یا کلیدی برای اتصال‌ها ذخیره نمی‌شود. راهنما: بخش «یکپارچه‌سازی‌ها» در راهنمای استقرار.</span>
</div>
{% endif %}

<section class="card mt-8" id="integration-connections">
    <div class="card-header border-0 pt-6">
        <div class="card-title flex-column">
            <h2>اتصال‌ها</h2>
            <span class="text-muted fs-7 mt-1">سامانه‌های بیرونی که به این استقرار وصل شده‌اند — هر کدام با وضعیت، آخرین بررسی و آخرین خطا.</span>
        </div>
        <div class="card-toolbar"><button class="btn btn-sm btn-primary" type="button" id="open-integration-dialog">افزودن اتصال</button></div>
    </div>
    <div class="card-body pt-2">
        <div id="integrations-loading" class="text-center text-gray-700 py-8">در حال دریافت اتصال‌ها…</div>
        <div id="integrations-empty" class="text-center text-gray-700 py-8" hidden>هنوز اتصالی ساخته نشده است.</div>
        <div id="integrations-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0">
            <thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>نام</th><th>نوع</th><th>وضعیت</th><th>آخرین بررسی</th><th>روشن</th><th>عملیات</th></tr></thead>
            <tbody id="integrations-table-body"></tbody>
        </table></div>
    </div>
</section>

{% if "outbound_webhooks" in features %}
<section class="card mt-8" id="integration-webhooks">
    <div class="card-header border-0 pt-6">
        <div class="card-title flex-column">
            <h2>وب‌هوک‌های خروجی</h2>
            <span class="text-muted fs-7 mt-1">رویدادهای دلفین (تماس، پیام، پرداخت) به نشانی سامانه‌های دیگر فرستاده می‌شود، امضاشده با HMAC-SHA256 و با تلاش دوباره.</span>
        </div>
        <div class="card-toolbar"><button class="btn btn-sm btn-primary" type="button" id="open-subscription-dialog">افزودن وب‌هوک</button></div>
    </div>
    <div class="card-body pt-2">
        <div id="subscriptions-loading" class="text-center text-gray-700 py-8">در حال دریافت…</div>
        <div id="subscriptions-empty" class="text-center text-gray-700 py-8" hidden>وب‌هوکی تعریف نشده است.</div>
        <div id="subscriptions-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0">
            <thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>نام</th><th>نشانی</th><th>رویدادها</th><th>کلید</th><th>روشن</th><th>عملیات</th></tr></thead>
            <tbody id="subscriptions-table-body"></tbody>
        </table></div>
    </div>
</section>
{% endif %}

{% if "public_api" in features %}
<section class="card mt-8" id="integration-tokens">
    <div class="card-header border-0 pt-6">
        <div class="card-title flex-column">
            <h2>توکن‌های API</h2>
            <span class="text-muted fs-7 mt-1">هر توکن به یک کاربر گره می‌خورد و دقیقاً همان دسترسی او را دارد، نه بیشتر؛ توکن «فقط خواندن» هیچ تغییری نمی‌تواند بدهد. مقدار توکن فقط یک بار، هنگام ساخت، نمایش داده می‌شود.</span>
        </div>
        <div class="card-toolbar"><button class="btn btn-sm btn-primary" type="button" id="open-token-dialog">ساخت توکن</button></div>
    </div>
    <div class="card-body pt-2">
        <div id="tokens-loading" class="text-center text-gray-700 py-8">در حال دریافت…</div>
        <div id="tokens-empty" class="text-center text-gray-700 py-8" hidden>توکنی ساخته نشده است.</div>
        <div id="tokens-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0">
            <thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>نام</th><th>کاربر</th><th>پیشوند</th><th>دامنه</th><th>آخرین استفاده</th><th>وضعیت</th><th>عملیات</th></tr></thead>
            <tbody id="tokens-table-body"></tbody>
        </table></div>
    </div>
</section>
{% endif %}

<section class="card mt-8" id="integration-logs">
    <div class="card-header border-0 pt-6">
        <div class="card-title flex-column">
            <h2>گزارش رویدادها</h2>
            <span class="text-muted fs-7 mt-1">آنچه از اتصال‌ها آمده و به آن‌ها رفته، تازه‌ترین بالا؛ رمزها و کلیدها پیش از ثبت حذف می‌شوند.</span>
        </div>
        <div class="card-toolbar"><select id="integration-logs-filter" class="form-select form-select-sm form-select-solid w-auto" aria-label="اتصال"><option value="">همهٔ اتصال‌ها</option></select></div>
    </div>
    <div class="card-body pt-2">
        <div id="logs-loading" class="text-center text-gray-700 py-8">در حال دریافت…</div>
        <div id="logs-empty" class="text-center text-gray-700 py-8" hidden>رویدادی ثبت نشده است.</div>
        <div id="logs-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-7 gy-3 mb-0">
            <thead><tr class="text-start text-gray-700 fw-bold fs-8 text-uppercase gs-0"><th>زمان</th><th>جهت</th><th>رویداد</th><th>نتیجه</th><th>شرح</th></tr></thead>
            <tbody id="logs-table-body"></tbody>
        </table></div>
        <nav id="logs-pagination" class="d-flex align-items-center justify-content-between flex-wrap gap-3 mt-6 pt-4 border-top border-gray-200" aria-label="صفحه‌بندی گزارش" hidden><button id="logs-prev" class="btn btn-light" type="button">قبلی</button><span id="logs-page-label"></span><button id="logs-next" class="btn btn-light" type="button">بعدی</button></nav>
    </div>
</section>

<dialog id="integration-dialog" aria-labelledby="integration-dialog-title">
    <form id="integration-form" novalidate>
        <div class="d-flex flex-stack align-items-center mb-5"><h2 id="integration-dialog-title" class="mb-0">افزودن اتصال</h2><button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button></div>
        <div class="row g-5">
            <div class="col-md-6"><label class="form-label fw-semibold required" for="integration-provider">نوع اتصال</label><select class="form-select form-select-solid" id="integration-provider" name="provider_key" required></select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="provider_key"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold required" for="integration-name">نام</label><input class="form-control form-control-solid" id="integration-name" name="name" required maxlength="120"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="name"></p></div>
            <p class="col-12 text-muted fs-7 mb-0" id="integration-provider-description"></p>
            <div class="col-12"><div class="row g-5" id="integration-fields"></div></div>
            <div class="col-12 d-flex align-items-center gap-3"><input class="form-check-input" id="integration-enabled" name="enabled" type="checkbox"><label class="form-label fw-semibold mb-0" for="integration-enabled">روشن باشد</label></div>
            <p class="col-12 text-danger fs-8 mb-0" data-error-for="secrets"></p>
        </div>
        <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-light" type="button" data-close-dialog>انصراف</button><button class="btn btn-primary" type="submit">ذخیره</button></div>
    </form>
</dialog>

<dialog id="subscription-dialog" aria-labelledby="subscription-dialog-title">
    <form id="subscription-form" novalidate>
        <div class="d-flex flex-stack align-items-center mb-5"><h2 id="subscription-dialog-title" class="mb-0">وب‌هوک خروجی</h2><button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button></div>
        <div class="row g-5">
            <div class="col-md-6"><label class="form-label fw-semibold required" for="subscription-name">نام</label><input class="form-control form-control-solid" id="subscription-name" name="name" required maxlength="120"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="name"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold required" for="subscription-url">نشانی (https)</label><input class="form-control form-control-solid" id="subscription-url" name="url" type="url" required maxlength="500" dir="ltr" placeholder="https://"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="url"></p></div>
            <fieldset class="col-12"><legend class="form-label fw-semibold fs-6">رویدادها <span class="text-muted fs-8 fw-normal">(هیچ‌کدام = همه)</span></legend><div class="d-flex flex-wrap gap-4" id="subscription-events"></div><p class="text-danger fs-8 mt-1 mb-0" data-error-for="event_types"></p></fieldset>
        </div>
        <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-light" type="button" data-close-dialog>انصراف</button><button class="btn btn-primary" type="submit">ذخیره</button></div>
    </form>
</dialog>

<dialog id="token-dialog" aria-labelledby="token-dialog-title">
    <form id="token-form" novalidate>
        <div class="d-flex flex-stack align-items-center mb-5"><h2 id="token-dialog-title" class="mb-0">ساخت توکن API</h2><button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button></div>
        <div class="row g-5">
            <div class="col-md-6"><label class="form-label fw-semibold required" for="token-name">نام</label><input class="form-control form-control-solid" id="token-name" name="name" required maxlength="120" placeholder="مثلاً ربات فروش"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="name"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold required" for="token-user">به نام کاربر</label><select class="form-select form-select-solid" id="token-user" name="user" required>{% for pk, name in token_users %}<option value="{{ pk }}">{{ name }}</option>{% endfor %}</select><p class="text-muted fs-8 mt-1 mb-0">یک کاربر اختصاصی با کمترین دسترسی لازم؛ مدیر پلتفرم مجاز نیست.</p><p class="text-danger fs-8 mt-1 mb-0" data-error-for="user"></p></div>
            <fieldset class="col-md-6"><legend class="form-label fw-semibold fs-6">دامنه</legend><div class="d-flex gap-5"><label class="d-flex align-items-center gap-2"><input class="form-check-input" type="checkbox" name="scopes" value="read" checked>خواندن</label><label class="d-flex align-items-center gap-2"><input class="form-check-input" type="checkbox" name="scopes" value="write">نوشتن</label></div><p class="text-danger fs-8 mt-1 mb-0" data-error-for="scopes"></p></fieldset>
            <div class="col-md-6"><label class="form-label fw-semibold" for="token-expires">انقضا (اختیاری)</label><input class="form-control form-control-solid" id="token-expires" name="expires_at" type="text" data-jalali="datetime"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="expires_at"></p></div>
        </div>
        <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-light" type="button" data-close-dialog>انصراف</button><button class="btn btn-primary" type="submit">ساخت توکن</button></div>
    </form>
</dialog>

<dialog id="secret-once-dialog" aria-labelledby="secret-once-title">
    <div class="d-flex flex-stack align-items-center mb-5"><h2 id="secret-once-title" class="mb-0">همین حالا ذخیره‌اش کنید</h2><button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button></div>
    <p class="text-gray-700" id="secret-once-note"></p>
    <div class="d-flex gap-3 align-items-center"><input class="form-control form-control-solid" id="secret-once-value" readonly dir="ltr" aria-label="مقدار"><button class="btn btn-light-primary" type="button" id="secret-once-copy">رونوشت</button></div>
    <p class="text-danger fs-7 mt-4 mb-0">این مقدار دیگر هرگز نمایش داده نمی‌شود؛ دلفین فقط اثر رمزنگاری‌شدهٔ آن را نگه می‌دارد.</p>
    <div class="d-flex justify-content-end mt-6"><button class="btn btn-primary" type="button" data-close-dialog>ذخیره کردم</button></div>
</dialog>
