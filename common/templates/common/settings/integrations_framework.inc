{% comment %} چارچوب یکپارچه‌سازی (۲.۲۱.۰؛ زبانه‌ها از ۲.۲۴.۰): داخلی‌های تلفن،
   وب‌هوک‌های خروجی، توکن‌های API و گزارش رویدادها، هرکدام یک زبانه؛ فهرست اتصال‌ها
   در خود `integrations.html` است. فقط برای مدیر پلتفرم و فقط وقتی ویژگی‌اش روشن
   است؛ هر API پشت این بخش‌ها همین دو را دوباره بررسی می‌کند. فرم هر نوع اتصال از
   فهرست فیلدهای خود ارائه‌دهنده ساخته می‌شود (`integrations/providers`). رمزها فقط
   نوشتنی‌اند: هرگز از سرور خوانده نمی‌شوند، فقط چند نویسهٔ آخرشان دیده می‌شود. {% endcomment %}
{% if "telephony" in features %}
<section id="profile-pane-extensions" role="tabpanel" aria-labelledby="profile-tab-extensions" data-profile-pane="extensions"{% if active_tab != "extensions" %} hidden{% endif %}>
<section class="card" id="integration-extensions">
    <div class="card-header border-0 pt-6">
        <div class="card-title flex-column">
            <h2>داخلی‌های تلفن</h2>
            <span class="text-muted fs-7 mt-1">هر داخلی مرکز تلفن به یک کاربر دلفین نسبت داده می‌شود تا تماس‌هایش به نام او ثبت شود و پنجرهٔ تماس ورودی برایش باز شود. هر کاربر یک داخلی فعال دارد.</span>
        </div>
        <div class="card-toolbar"><button class="btn btn-sm btn-primary" type="button" id="open-extension-dialog">افزودن داخلی</button></div>
    </div>
    <div class="card-body pt-2">
        <div id="extensions-loading" class="text-center text-gray-700 py-8">در حال دریافت…</div>
        <div id="extensions-empty" class="text-center text-gray-700 py-8" hidden>داخلی‌ای تعریف نشده است. تا وقتی داخلی‌ها تعریف نشوند، تماس‌ها ثبت می‌شوند ولی به نام کسی نیستند.</div>
        <div id="extensions-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0">
            <thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>داخلی</th><th>مرکز تلفن</th><th>کاربر</th><th>برچسب</th><th>فعال</th><th>عملیات</th></tr></thead>
            <tbody id="extensions-table-body"></tbody>
        </table></div>
    </div>
</section>
</section>

<dialog id="extension-dialog" aria-labelledby="extension-dialog-title">
    <form id="extension-form" novalidate>
        <div class="d-flex flex-stack align-items-center mb-5"><h2 id="extension-dialog-title" class="mb-0">افزودن داخلی</h2><button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button></div>
        <div class="row g-5">
            <div class="col-md-6"><label class="form-label fw-semibold required" for="extension-integration">مرکز تلفن</label><select class="form-select form-select-solid" id="extension-integration" name="integration" required></select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="integration"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold required" for="extension-number">شمارهٔ داخلی</label><input class="form-control form-control-solid" id="extension-number" name="number" required maxlength="20" inputmode="numeric" dir="ltr" placeholder="201"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="number"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold" for="extension-user">کاربر</label><select class="form-select form-select-solid" id="extension-user" name="user"><option value="">— بدون کاربر —</option>{% for pk, name in telephony_users %}<option value="{{ pk }}">{{ name }}</option>{% endfor %}</select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="user"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold" for="extension-label">برچسب</label><input class="form-control form-control-solid" id="extension-label" name="label" maxlength="120" placeholder="مثلاً میز پذیرش"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="label"></p></div>
            <div class="col-12 d-flex align-items-center gap-3"><input class="form-check-input" id="extension-active" name="active" type="checkbox" checked><label class="form-label fw-semibold mb-0" for="extension-active">فعال</label></div>
        </div>
        <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-light" type="button" data-close-dialog>انصراف</button><button class="btn btn-primary" type="submit">ذخیره</button></div>
    </form>
</dialog>
{% endif %}

{% if "outbound_webhooks" in features %}
<section id="profile-pane-webhooks" role="tabpanel" aria-labelledby="profile-tab-webhooks" data-profile-pane="webhooks"{% if active_tab != "webhooks" %} hidden{% endif %}>
<section class="card" id="integration-webhooks">
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
</section>
{% endif %}

{% if "public_api" in features %}
<section id="profile-pane-tokens" role="tabpanel" aria-labelledby="profile-tab-tokens" data-profile-pane="tokens"{% if active_tab != "tokens" %} hidden{% endif %}>
<section class="card" id="integration-tokens">
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
</section>
{% endif %}

<section id="profile-pane-logs" role="tabpanel" aria-labelledby="profile-tab-logs" data-profile-pane="logs"{% if active_tab != "logs" %} hidden{% endif %}>
<section class="card" id="integration-logs">
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
</section>

<dialog id="integration-catalog-dialog" aria-labelledby="integration-catalog-title">
    <div class="d-flex flex-stack align-items-center mb-2"><h2 id="integration-catalog-title" class="mb-0">افزودن اتصال</h2><button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button></div>
    <p class="text-muted fs-7 mb-6">به چه سامانه‌ای می‌خواهید وصل شوید؟</p>
    <div class="row g-4" id="integration-catalog-providers" aria-label="اتصال‌های قابل ساخت"></div>
    {% if integrations %}
    <h3 class="fs-6 fw-bold text-gray-800 mt-8 mb-4">سرویس‌های داخلی پنل</h3>
    <div class="row g-4">
        {% for row in integrations %}
        <div class="col-md-6"><a class="btn btn-outline btn-outline-dashed btn-active-light-primary d-flex align-items-start text-start gap-4 p-5 w-100 h-100" href="{% url row.settings_url_name %}">
            <span class="symbol symbol-40px flex-shrink-0"><span class="symbol-label bg-light-primary"><i class="di-duotone {{ row.icon }} fs-2 text-primary" aria-hidden="true">{% for path in ""|ljust:row.icon_paths %}<span class="path{{ forloop.counter }}"></span>{% endfor %}</i></span></span>
            <span class="min-w-0"><span class="d-block fw-bold text-gray-900">{{ row.label }}</span><span class="d-block text-muted fs-8">{{ row.description }}</span></span>
        </a></div>
        {% endfor %}
    </div>
    {% endif %}
    {% if upcoming_services %}
    <h3 class="fs-6 fw-bold text-gray-800 mt-8 mb-4">به‌زودی</h3>
    <ul class="row g-4 list-unstyled mb-0" data-upcoming-services>
        {% for service in upcoming_services %}
        <li class="col-md-6"><div class="d-flex align-items-start gap-4 p-5 h-100 rounded border border-dashed border-gray-300" data-upcoming="{{ service.key }}">
            <span class="symbol symbol-40px flex-shrink-0"><span class="symbol-label bg-light"><i class="di-duotone {{ service.icon }} fs-2 text-gray-500" aria-hidden="true">{% for path in ""|ljust:service.icon_paths %}<span class="path{{ forloop.counter }}"></span>{% endfor %}</i></span></span>
            <span class="min-w-0 flex-grow-1"><span class="d-flex align-items-center gap-2 fw-bold text-gray-700">{{ service.label }} <span class="badge badge-light fs-9">به‌زودی</span></span><span class="d-block text-muted fs-8">{{ service.description }}</span></span>
        </div></li>
        {% endfor %}
    </ul>
    {% endif %}
</dialog>

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
