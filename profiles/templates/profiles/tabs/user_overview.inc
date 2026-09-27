{% load jalali_tags %}
<div class="row g-5 g-xl-8">
    <div class="col-xl-5">
        <section class="card h-100"><div class="card-body">
            <div class="d-flex flex-stack align-items-center mb-5">
                <h2 class="fs-3 fw-bold text-gray-900 mb-0">دربارهٔ {% if is_own_profile %}من{% else %}این کاربر{% endif %}</h2>
                {% if profile_edit_mode %}<a class="btn btn-sm btn-light" href="?tab=info" data-profile-tab-link="info">ویرایش</a>{% endif %}
            </div>
            {% with account=person_object %}
            <dl class="mb-0">
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">نام کاربری</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break"><span dir="ltr">{{ account.username }}</span></dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">نقش</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break">{{ person.role_label }}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">سمت</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break" data-overview-field="job_title">{{ account.job_title|default:"—" }}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">استان</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break" data-overview-field="province">{{ account.province|default:"—" }}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">ایمیل</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break"><span data-overview-field="email" dir="ltr">{{ account.email|default:"—" }}</span></dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">وضعیت</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break">{% if account.is_active %}فعال{% else %}غیرفعال{% endif %}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">آخرین ورود</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break">{% if account.last_login %}{{ account.last_login|jalali_datetime }}{% else %}<span title="این حساب هنوز وارد نشده است.">—</span>{% endif %}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">آخرین بازدید</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break">{% if account.last_seen_at %}{{ account.last_seen_at|jalali_datetime }}{% else %}<span title="از نسخهٔ ۲.۱۹.۰ به بعد ثبت می‌شود و هنوز بازدیدی ثبت نشده است.">—</span>{% endif %}</dd></div>
                <div class="row mb-5"><dt class="col-5 fw-semibold text-muted">تاریخ ایجاد حساب</dt><dd class="col-7 fw-bold fs-6 text-gray-800 mb-0 text-break">{{ account.created_at|jalali_datetime }}</dd></div>
            </dl>
            {% endwith %}
        </div></section>
    </div>
    <div class="col-xl-7">
        {% include "profiles/tabs/recent_activity.inc" %}
    </div>
</div>
