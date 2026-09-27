{% comment %} تماس‌های مرکز تلفن که این همکار پاسخ داده یا گرفته (۲.۲۳.۰) — برای خود او با
   `calls.own` و برای دارندهٔ `calls.company`. داخلی‌های او همان‌هایی‌اند که مدیر پلتفرم در
   «یکپارچه‌سازی‌ها» به نامش ثبت کرده است. {% endcomment %}
{% load jalali_tags %}
<section class="card mb-5 mb-xl-8" data-pbx-calls="user"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center gap-3 mb-5">
        <h2 class="fs-3 fw-bold text-gray-900 mb-0">تماس‌های مرکز تلفن</h2>
        <div class="d-flex flex-wrap gap-2" data-person-extensions>
            {% for extension in person_extensions %}
            <span class="badge badge-light-primary fs-7" title="{{ extension.integration.name }}{% if extension.label %} — {{ extension.label }}{% endif %}">داخلی {{ extension.number|persian_digits }}</span>
            {% empty %}
            <span class="text-muted fs-7" title="مدیر پلتفرم در «یکپارچه‌سازی‌ها» داخلی را به کاربر نسبت می‌دهد.">داخلی تلفنی به نام این کاربر ثبت نشده است.</span>
            {% endfor %}
        </div>
    </div>
    {% include "profiles/tabs/pbx_calls_table.inc" with prefix="user-pbx-calls" empty_text="تماسی از مرکز تلفن برای این کاربر ثبت نشده است." show_person=True %}
</div></section>
