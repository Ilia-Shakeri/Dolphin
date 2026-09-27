{% comment %} تماس‌های ثبت‌شدهٔ دستی (Interaction). تماس‌های مرکز تلفن (VoIP)
   وقتی اتصال تلفنی روشن باشد به همین زبانه اضافه می‌شوند. {% endcomment %}
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center mb-4"><h2 class="fs-3 fw-bold text-gray-900 mb-5">تماس‌های ثبت‌شده</h2></div>
    <div id="customer-interactions-loading" class="text-center text-gray-700 py-10">در حال دریافت تماس‌ها…</div><div id="customer-interactions-empty" class="text-center text-gray-700 py-10" hidden>تماسی برای این مشتری در محدوده دسترسی شما نیست.</div>
    <div id="customer-interactions-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0"><thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>مشتری</th><th>شماره</th><th>جهت</th><th>نتیجه</th><th>زمان</th><th>پیگیری بعدی</th><th>عملیات</th></tr></thead><tbody id="customer-interactions-table-body"></tbody></table></div>
    <nav id="customer-interactions-pagination" class="d-flex align-items-center justify-content-between flex-wrap gap-3 mt-6 pt-4 border-top border-gray-200" aria-label="صفحه‌بندی تماس‌های مرتبط" hidden><button id="customer-interactions-prev" class="btn btn-light" type="button">قبلی</button><span id="customer-interactions-page-label"></span><button id="customer-interactions-next" class="btn btn-light" type="button">بعدی</button></nav>
</div></section>
