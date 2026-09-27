{% comment %} جدول تماس‌های مرکز تلفن (۲.۲۳.۰)، مشترک میان زبانهٔ تماس‌های مشتری و کاربر.
   ردیف‌ها را `loadPbxCalls` در dolphin-app.js از `/api/v1/calls/` پر می‌کند؛ دکمهٔ
   «پخش» فقط برای کسی ساخته می‌شود که API برایش `has_recording` برگرداند. {% endcomment %}
<div id="{{ prefix }}-loading" class="text-center text-gray-700 py-10">در حال دریافت تماس‌ها…</div>
<div id="{{ prefix }}-empty" class="text-center text-gray-700 py-10" hidden>{{ empty_text }}</div>
<div id="{{ prefix }}-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0">
    <thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>تماس</th>{% if show_person %}<th>مخاطب</th>{% endif %}<th>شماره</th><th>داخلی</th><th>زمان</th><th>مکالمه</th><th>ضبط و عملیات</th></tr></thead>
    <tbody id="{{ prefix }}-table-body" data-show-person="{% if show_person %}1{% endif %}"></tbody>
</table></div>
<nav id="{{ prefix }}-pagination" class="d-flex align-items-center justify-content-between flex-wrap gap-3 mt-6 pt-4 border-top border-gray-200" aria-label="صفحه‌بندی تماس‌های مرکز تلفن" hidden><button id="{{ prefix }}-prev" class="btn btn-light" type="button">قبلی</button><span id="{{ prefix }}-page-label"></span><button id="{{ prefix }}-next" class="btn btn-light" type="button">بعدی</button></nav>
