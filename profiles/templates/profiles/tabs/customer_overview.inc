{% load jalali_tags customer_kind_tags %}
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
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">نشانی</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break" data-overview-field="address">{{ customer.address|default:"—" }}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">ثبت‌کننده</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break">{{ customer.created_by.get_full_name|default:customer.created_by.username }}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">تاریخ ثبت</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break">{{ customer.created_at|jalali_datetime }}</dd></div>
            </dl>
            {% if customer.notes %}<div class="mt-5 pt-4 border-top border-gray-200"><h3 class="fs-6 fw-bold text-gray-800 mb-2">یادداشت</h3><p class="text-gray-700 mb-0 text-break" data-overview-field="notes">{{ customer.notes|linebreaksbr }}</p></div>{% endif %}
            {% endwith %}
        </div></section>
    </div>
    <div class="col-xl-7">
        {% include "profiles/tabs/recent_activity.inc" %}
    </div>
</div>
