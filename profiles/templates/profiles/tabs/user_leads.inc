{% comment %} The leads assigned to this user, with the customer behind each —
   filtered by `assigned_to` on the ordinary leads API, so the reader's own
   lead scope (`leads_for`) still decides which of them appear. {% endcomment %}
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center gap-3 mb-4">
        <h2 class="fs-3 fw-bold text-gray-900 mb-0">سرنخ‌های واگذارشده</h2>
        <select class="form-select form-select-solid form-select-sm w-auto" id="user-leads-status" aria-label="وضعیت سرنخ">
            <option value="">همهٔ وضعیت‌ها</option>
            <option value="pending">در انتظار تکمیل</option>
            <option value="completed">تکمیل</option>
            <option value="cancelled">کنسل شده</option>
        </select>
    </div>
    <div id="user-leads-loading" class="text-center text-gray-700 py-10">در حال دریافت سرنخ‌ها…</div><div id="user-leads-empty" class="text-center text-gray-700 py-10" hidden>سرنخی به این کاربر در محدودهٔ دسترسی شما واگذار نشده است.</div>
    <div id="user-leads-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0"><thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>مشتری</th><th>منبع</th><th>کمپین</th><th>وضعیت</th><th>پیگیری بعدی</th><th>تاریخ واگذاری</th><th>عملیات</th></tr></thead><tbody id="user-leads-table-body"></tbody></table></div>
    <nav id="user-leads-pagination" class="d-flex align-items-center justify-content-between flex-wrap gap-3 mt-6 pt-4 border-top border-gray-200" aria-label="صفحه‌بندی سرنخ‌ها" hidden><button id="user-leads-prev" class="btn btn-light" type="button">قبلی</button><span id="user-leads-page-label"></span><button id="user-leads-next" class="btn btn-light" type="button">بعدی</button></nav>
</div></section>
