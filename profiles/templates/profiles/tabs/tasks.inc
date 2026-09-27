{% comment %} وظیفه‌ها — برای مشتری، وظیفه‌هایی که دربارهٔ اوست؛ برای کاربر، وظیفه‌هایی
   که به او واگذار شده. دامنهٔ خود خواننده (`tasks_for`) تعیین می‌کند کدام‌ها
   دیده شوند. {% endcomment %}
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center gap-3 mb-4">
        <h2 class="fs-3 fw-bold text-gray-900 mb-0">{% if person.type == "customer" %}وظایفِ مربوط به این مشتری{% else %}وظایفِ واگذارشده به {{ person.name }}{% endif %}</h2>
        <div class="d-flex flex-wrap align-items-center gap-2">
            <select id="profile-tasks-status" class="form-select form-select-sm form-select-solid w-auto" aria-label="وضعیت وظیفه">
                <option value="open">باز</option>
                <option value="done">انجام‌شده</option>
                <option value="cancelled">لغوشده</option>
                <option value="">همه</option>
            </select>
            {% if can_add_task %}<button class="btn btn-sm btn-primary" type="button" data-profile-action="add-task">وظیفهٔ تازه</button>{% endif %}
        </div>
    </div>
    <div id="profile-tasks-loading" class="text-center text-gray-700 py-10">در حال دریافت وظیفه‌ها…</div>
    <div id="profile-tasks-empty" class="text-center text-gray-700 py-10" hidden>وظیفه‌ای با این وضعیت نیست.</div>
    <div id="profile-tasks-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0"><thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>عنوان</th><th>مسئول</th><th>سررسید</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody id="profile-tasks-table-body"></tbody></table></div>
    <nav id="profile-tasks-pagination" class="d-flex align-items-center justify-content-between flex-wrap gap-3 mt-6 pt-4 border-top border-gray-200" aria-label="صفحه‌بندی وظیفه‌ها" hidden><button id="profile-tasks-prev" class="btn btn-light" type="button">قبلی</button><span id="profile-tasks-page-label"></span><button id="profile-tasks-next" class="btn btn-light" type="button">بعدی</button></nav>
</div></section>
