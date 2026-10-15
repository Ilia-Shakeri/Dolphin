{% load jalali_tags customer_kind_tags %}
{% if can_use_assistant %}
{% comment %} The internal AI assistant (2.40.55, feature `ai_assistant`): it reads this
   customer as far as the reader may, and only suggests — nothing here changes the
   record or sends anything. `assistant.services`. {% endcomment %}
<section class="card mb-5 mb-xl-8" id="profile-assistant">
    <div class="card-header border-0 pt-6 flex-wrap gap-3">
        <div class="card-title flex-column">
            <h2 class="d-flex align-items-center gap-2"><i class="di-duotone di-technology-2 fs-2 text-primary" aria-hidden="true"><span class="path1"></span><span class="path2"></span></i>دستیار هوش مصنوعی</h2>
            <span class="text-muted fs-7 mt-1">روی سرور خود شرکت اجرا می‌شود و فقط پیشنهاد می‌دهد؛ چیزی را تغییر نمی‌دهد و نمی‌فرستد.</span>
        </div>
        <div class="card-toolbar d-flex flex-wrap gap-2">
            <button class="btn btn-sm btn-light-primary" type="button" data-assistant-kind="summary">خلاصهٔ پرونده</button>
            <button class="btn btn-sm btn-light-primary" type="button" data-assistant-kind="next_action">اقدام بعدی</button>
            <button class="btn btn-sm btn-light-primary" type="button" data-assistant-kind="sms_draft">پیش‌نویس پیامک</button>
        </div>
    </div>
    <div class="card-body pt-2">
        <div class="mb-4" id="profile-assistant-goal-field">
            <label class="form-label fs-7" for="profile-assistant-goal">هدف پیامک (اختیاری)</label>
            <input class="form-control form-control-solid form-control-sm" id="profile-assistant-goal" maxlength="200" placeholder="مثلاً یادآوری قسط یا دعوت به جشنواره">
        </div>
        <div id="profile-assistant-loading" class="text-gray-700 py-4" hidden>دستیار در حال آماده کردن پیشنهاد است…</div>
        <div id="profile-assistant-result" hidden>
            <h3 class="fs-6 fw-bold text-gray-900 mb-2" id="profile-assistant-title"></h3>
            <div class="bg-light rounded p-4 text-gray-800 text-break assistant-answer" id="profile-assistant-text"></div>
            <div class="d-flex flex-wrap align-items-center gap-3 mt-3">
                <button class="btn btn-sm btn-light" type="button" id="profile-assistant-copy">کپی متن</button>
                <span class="text-muted fs-8" id="profile-assistant-meta"></span>
            </div>
        </div>
        <p class="text-danger fs-7 mb-0" data-error-for="assistant"></p>
    </div>
</section>
{% endif %}
<div class="row g-5 g-xl-8">
    <div class="col-xl-5">
        <section class="card h-100"><div class="card-body">
            <div class="d-flex flex-stack align-items-center mb-5">
                <h2 class="fs-3 fw-bold text-gray-900 mb-0">دربارهٔ مشتری</h2>
                {% if "customers.manage" in capabilities %}<a class="btn btn-sm btn-light" href="?tab=info" data-profile-tab-link="info">ویرایش</a>{% endif %}
            </div>
            {% with customer=person_object %}
            <dl class="mb-0">
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">نوع</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break" data-overview-field="kind_display">{% customer_kind customer.kind %}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">سمت</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break" data-overview-field="job_title">{{ customer.job_title|default:"—" }}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">کد ملی</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break"><span data-overview-field="national_id" dir="ltr">{{ customer.national_id|default:"—"|persian_digits }}</span></dd></div>
                {% if customer.kind == "legal" or customer.economic_code %}<div class="row mb-5"><dt class="col-5 fw-semibold text-muted">شماره اقتصادی</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break"><span data-overview-field="economic_code" dir="ltr">{{ customer.economic_code|default:"—"|persian_digits }}</span></dd></div>{% endif %}
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">ایمیل</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break"><span data-overview-field="email" dir="ltr">{{ customer.email|default:"—" }}</span></dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">استان و شهر</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break" data-overview-field="place">{% if customer.province or customer.city %}{{ customer.province|default:"—" }}{% if customer.city %}، {{ customer.city }}{% endif %}{% else %}—{% endif %}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">کد پستی</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break"><span data-overview-field="postal_code" dir="ltr">{{ customer.postal_code|default:"—"|persian_digits }}</span></dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">دسته‌بندی</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break" data-overview-field="category">{{ customer.category|default:"—" }}</dd></div>
                {% for fact in custom_facts %}
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">{{ fact.label }}</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break" data-overview-field="{{ fact.key }}">{% if not fact.value %}—{% elif fact.field_type == "boolean" %}{% if fact.value == "true" %}بله{% else %}خیر{% endif %}{% elif fact.field_type == "date" %}{% panel_date fact.value %}{% elif fact.field_type == "number" %}{{ fact.value|persian_digits }}{% else %}{{ fact.value }}{% endif %}</dd></div>
                {% endfor %}
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">نشانی</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break" data-overview-field="address">{{ customer.address|default:"—" }}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">ثبت‌کننده</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break">{{ customer.created_by.get_full_name|default:customer.created_by.username }}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">تاریخ ثبت</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break">{% panel_date customer.created_at "datetime" %}</dd></div>
            </dl>
            {% if customer.notes %}<div class="mt-5 pt-4 border-top border-gray-200"><h3 class="fs-6 fw-bold text-gray-800 mb-2">یادداشت</h3><p class="text-gray-700 mb-0 text-break" data-overview-field="notes">{{ customer.notes|linebreaksbr }}</p></div>{% endif %}
            {% endwith %}
        </div></section>
    </div>
    <div class="col-xl-7">
        {% include "profiles/tabs/recent_activity.inc" %}
    </div>
</div>
