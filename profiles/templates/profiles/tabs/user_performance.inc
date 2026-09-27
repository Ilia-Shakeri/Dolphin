{% comment %} The performance page this profile replaced (`/users/<id>/profile/`,
   which now redirects here), moved into a tab unchanged: the same period
   filter, the same four figures, the same trend and the same drill-down, all
   read from the reports API with its own scope check on every request. {% endcomment %}
<section id="user-profile-content" data-target-user-id="{{ target_user_id }}" data-target-username="{{ target_username }}">
    <div class="card mb-5 mb-xl-8"><div class="card-body">
        <form id="profile-performance-filter-form" class="d-flex flex-wrap align-items-end gap-3" novalidate>
            <input type="hidden" id="profile-user-id" name="user_id" value="{{ target_user_id }}">
            <div><label class="form-label fw-semibold" for="profile-period-start">شروع بازه</label><input class="form-control form-control-solid form-control-sm" id="profile-period-start" name="period_start" type="text" data-jalali="datetime" required><p class="text-danger fs-8 mt-1 mb-0" data-error-for="period_start"></p></div>
            <div><label class="form-label fw-semibold" for="profile-period-end">پایان بازه</label><input class="form-control form-control-solid form-control-sm" id="profile-period-end" name="period_end" type="text" data-jalali="datetime" required><p class="text-danger fs-8 mt-1 mb-0" data-error-for="period_end"></p></div>
            <button class="btn btn-sm btn-primary" type="submit">به‌روزرسانی</button>
        </form>
        <div id="profile-performance-loading" class="text-center text-gray-700 py-6" hidden>در حال دریافت عملکرد…</div>
        <div id="profile-performance-error" class="text-center text-danger py-6" role="alert" hidden>عملکرد دریافت نشد.</div>
        <div class="d-flex flex-wrap mt-5">
            <div class="border border-gray-300 border-dashed rounded min-w-125px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-kpi="customers_created_count">—</div><div class="fw-semibold fs-6 text-gray-500">مشتری ثبت‌شده</div></div>
            <div class="border border-gray-300 border-dashed rounded min-w-125px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-kpi="sales_count">—</div><div class="fw-semibold fs-6 text-gray-500">فروش تأییدشده</div></div>
            <div class="border border-gray-300 border-dashed rounded min-w-150px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-kpi="sales_amount">—</div><div class="fw-semibold fs-6 text-gray-500">مبلغ فروش تأییدشده</div></div>
            <div class="border border-gray-300 border-dashed rounded min-w-150px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-kpi="average_sale_amount">—</div><div class="fw-semibold fs-6 text-gray-500">میانگین مبلغ فروش</div></div>
        </div>
    </div></div>

    {% if sees_person_calls %}
    {% comment %} تماس‌های مرکز تلفن همین کاربر در همین بازه (۲.۲۳.۰)، از
       `/api/v1/telephony/stats/`، که دسترسی را دوباره می‌سنجد. {% endcomment %}
    <div class="card mb-5 mb-xl-8" data-call-stats><div class="card-body">
        <h2 class="fs-3 fw-bold text-gray-900 mb-1">تماس‌های مرکز تلفن در همین بازه</h2>
        <p class="text-muted fs-7 mb-5">تماس‌هایی که به داخلی این کاربر رسیده یا از آن گرفته شده؛ «پیگیری» یعنی تماس بی‌پاسخ ظرف ۲۴ ساعت با همان شماره دوباره گرفته شده یا وظیفهٔ پیگیری‌اش انجام شده است.</p>
        <div id="profile-call-stats-loading" class="text-center text-gray-700 py-6" hidden>در حال دریافت تماس‌ها…</div>
        <div id="profile-call-stats-error" class="text-center text-danger py-6" role="alert" hidden>آمار تماس دریافت نشد.</div>
        <div class="d-flex flex-wrap">
            <div class="border border-gray-300 border-dashed rounded min-w-125px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-call-stat="inbound">—</div><div class="fw-semibold fs-6 text-gray-500">تماس ورودی</div></div>
            <div class="border border-gray-300 border-dashed rounded min-w-125px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-call-stat="inbound_answered">—</div><div class="fw-semibold fs-6 text-gray-500">پاسخ‌داده</div></div>
            <div class="border border-gray-300 border-dashed rounded min-w-125px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-call-stat="missed">—</div><div class="fw-semibold fs-6 text-gray-500">بی‌پاسخ</div></div>
            <div class="border border-gray-300 border-dashed rounded min-w-125px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-call-stat="outbound">—</div><div class="fw-semibold fs-6 text-gray-500">تماس خروجی</div></div>
            <div class="border border-gray-300 border-dashed rounded min-w-125px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-call-stat="talk_seconds">—</div><div class="fw-semibold fs-6 text-gray-500">زمان مکالمه</div></div>
            <div class="border border-gray-300 border-dashed rounded min-w-125px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-call-stat="average_talk_seconds">—</div><div class="fw-semibold fs-6 text-gray-500">میانگین هر مکالمه</div></div>
            <div class="border border-gray-300 border-dashed rounded min-w-150px py-3 px-4 me-6 mb-3"><div class="fs-2 fw-bold" data-call-stat="follow_up">—</div><div class="fw-semibold fs-6 text-gray-500">بی‌پاسخ‌های پیگیری‌شده</div></div>
        </div>
    </div></div>
    {% endif %}

    <div class="row g-5 g-xl-8">
        <div class="col-xl-7">
            <section class="card h-100"><div class="card-body">
                <div class="d-flex flex-wrap flex-stack align-items-center gap-3 mb-4">
                    <h2 class="fs-3 fw-bold text-gray-900 mb-0">روند فروش تأییدشده</h2>
                    <div id="profile-trend-controls"></div>
                </div>
                <p class="text-muted fs-7 mb-5">مبلغ فروش تأییدشده این کاربر در بازه‌ای که انتخاب می‌کنید. عرض هر سطل از طول همان بازه درمی‌آید، و سطل بدون فروش با صفر رسم می‌شود تا شیب نمودار درست بماند.</p>
                <div id="profile-trend-chart" role="img" aria-label="نمودار روند فروش تأییدشده" hidden></div>
                <p id="profile-trend-chart-empty" class="text-center text-gray-700 py-10" hidden>در یک سال اخیر فروش تأییدشده‌ای ثبت نشده است.</p>
            </div></section>
        </div>
        <div class="col-xl-5">
            <section class="card h-100"><div class="card-body">
                <h2 class="fs-3 fw-bold text-gray-900 mb-4">جزئیات همین بازه</h2>
                <div class="d-flex flex-wrap gap-3 mb-5">
                    <button class="btn btn-light" type="button" data-performance-detail="customers_created_count">مشتری‌های پشت این عدد</button>
                    <button class="btn btn-light" type="button" data-performance-detail="sales_count">فروش‌های پشت این عدد</button>
                </div>
                <section id="profile-performance-details" hidden>
                    <p id="profile-details-scope" class="text-muted mb-4"></p>
                    <div id="profile-details-loading" class="text-center text-gray-700 py-10" hidden>در حال دریافت جزئیات…</div>
                    <div id="profile-details-error" class="text-center text-danger py-10" role="alert" hidden>جزئیات دریافت نشد.</div>
                    <div id="profile-details-empty" class="text-center text-gray-700 py-10" hidden>رکوردی برای این شاخص نیست.</div>
                    <div id="profile-details-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0"><thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>نوع</th><th>مشتری</th><th>کاربر</th><th>محصول</th><th>مبلغ</th><th>زمان</th><th>عمل</th></tr></thead><tbody id="profile-details-body"></tbody></table></div>
                    <nav id="profile-details-pagination" class="d-flex align-items-center justify-content-between flex-wrap gap-3 mt-6 pt-4 border-top border-gray-200" aria-label="صفحه‌بندی جزئیات" hidden><button id="profile-details-prev" class="btn btn-light" type="button">قبلی</button><span id="profile-details-page-label"></span><button id="profile-details-next" class="btn btn-light" type="button">بعدی</button></nav>
                </section>
            </div></section>
        </div>
    </div>
</section>
