<section class="card mb-5 mb-xl-8" data-performance-panel="{{ panel_prefix }}" data-company-scope="{{ can_view_company_reports|yesno:'true,false' }}" aria-labelledby="{{ panel_prefix }}-performance-title"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center mb-4">
        <div>
            <h2 id="{{ panel_prefix }}-performance-title">{% if can_view_company_reports %}عملکرد عملیاتی شرکت{% else %}عملکرد عملیاتی من{% endif %}</h2>
            <p class="text-muted">مشتری‌های ثبت‌شده و فروش‌های تأییدشده در بازه انتخابی.</p>
        </div>
    </div>
    <form id="{{ panel_prefix }}-performance-filter-form" class="mt-5" action="/api/v1/reports/user-performance/" method="get" novalidate>
        <div class="row g-5">
            <div class="col-md-6 col-xl-3"><label class="form-label fw-semibold" for="{{ panel_prefix }}-period-start">شروع بازه</label><input class="form-control form-control-solid" id="{{ panel_prefix }}-period-start" name="period_start" type="text" data-jalali="datetime" required><p class="text-danger fs-8 mt-1 mb-0" data-error-for="period_start"></p></div>
            <div class="col-md-6 col-xl-3"><label class="form-label fw-semibold" for="{{ panel_prefix }}-period-end">پایان بازه</label><input class="form-control form-control-solid" id="{{ panel_prefix }}-period-end" name="period_end" type="text" data-jalali="datetime" required><p class="text-danger fs-8 mt-1 mb-0" data-error-for="period_end"></p></div>
            {% if can_view_company_reports %}<div class="col-md-6 col-xl-3"><label class="form-label fw-semibold" for="{{ panel_prefix }}-user">کاربر</label><select class="form-select form-select-solid" id="{{ panel_prefix }}-user" name="user_id"><option value="">همه کاربران مجاز</option></select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="user_id"></p></div>{% endif %}
            <div class="col-md-6 col-xl-3"><label class="form-label fw-semibold" for="{{ panel_prefix }}-product">محصول فروش</label><select class="form-select form-select-solid" id="{{ panel_prefix }}-product" name="sales_product_id"><option value="">همه محصولات مجاز</option></select><p class="muted field-hint">این فیلتر فقط شاخص‌های فروش را تغییر می‌دهد.</p><p class="text-danger fs-8 mt-1 mb-0" data-error-for="sales_product_id"></p></div>
            <div class="col-12 d-flex justify-content-end gap-3"><a id="{{ panel_prefix }}-performance-xlsx" class="btn btn-light" href="/api/v1/exports/user-performance.xlsx" download>دریافت XLSX</a><button class="btn btn-primary" type="submit">به‌روزرسانی</button></div>
        </div>
    </form>
    <div id="{{ panel_prefix }}-performance-loading" class="text-center text-gray-700 py-10" hidden>در حال دریافت عملکرد…</div>
    <div id="{{ panel_prefix }}-performance-error" class="text-center text-danger py-10" role="alert" hidden>گزارش دریافت نشد. دوباره تلاش کنید.</div>
    <div id="{{ panel_prefix }}-performance-empty" class="text-center text-gray-700 py-10" hidden>در این بازه مشتری تازه یا فروش تأییدشده‌ای ثبت نشده است.</div>
    <div id="{{ panel_prefix }}-performance-content" hidden>
        <div class="row g-5 mb-6" aria-label="شاخص‌های قطعی عملکرد">
            <div class="col-sm-6 col-xl-3"><div class="card card-flush h-100"><div class="card-body py-5"><span class="text-muted fw-semibold fs-7 d-block">مشتری ثبت‌شده</span><span class="text-gray-900 fw-bolder fs-2x mt-2 d-block" data-kpi="customers_created_count">۰</span></div></div></div>
            <div class="col-sm-6 col-xl-3"><div class="card card-flush h-100"><div class="card-body py-5"><span class="text-muted fw-semibold fs-7 d-block">تعداد فروش تأییدشده</span><span class="text-gray-900 fw-bolder fs-2x mt-2 d-block" data-kpi="sales_count">۰</span></div></div></div>
            <div class="col-sm-6 col-xl-3"><div class="card card-flush h-100"><div class="card-body py-5"><span class="text-muted fw-semibold fs-7 d-block">مبلغ فروش تأییدشده</span><span class="text-gray-900 fw-bolder fs-2x mt-2 d-block" data-kpi="sales_amount">۰.۰۰</span></div></div></div>
            <div class="col-sm-6 col-xl-3"><div class="card card-flush h-100"><div class="card-body py-5"><span class="text-muted fw-semibold fs-7 d-block">میانگین مبلغ فروش تأییدشده</span><span class="text-gray-900 fw-bolder fs-2x mt-2 d-block" data-kpi="average_sale_amount">۰.۰۰</span></div></div></div>
        </div>
        <div class="d-flex flex-wrap gap-3 mb-5">
            <button class="btn btn-light" type="button" data-performance-detail="customers_created_count">مشتری‌های پشت این جمع</button>
            <button class="btn btn-light" type="button" data-performance-detail="sales_count">فروش‌های پشت این جمع</button>
        </div>
        <div class="row g-5">
            <section class="col-lg-5" aria-labelledby="{{ panel_prefix }}-chart-title">
                <h3 id="{{ panel_prefix }}-chart-title">مبلغ فروش تأییدشده به تفکیک کاربر</h3>
                <div id="{{ panel_prefix }}-performance-chart" class="performance-chart" role="img" aria-label="نمودار مبلغ فروش تأییدشده کاربران مجاز"></div>
                <p id="{{ panel_prefix }}-performance-chart-empty" class="text-center text-gray-700 py-10" hidden>فروش تأییدشده‌ای برای نمودار نیست.</p>
            </section>
            <section class="col-lg-7" aria-labelledby="{{ panel_prefix }}-table-title">
                <h3 id="{{ panel_prefix }}-table-title">جزئیات همان محدوده مجاز</h3>
                <div class="table-responsive"><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0"><thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>کاربر</th><th>مشتری ثبت‌شده</th><th>فروش تأییدشده</th><th>مبلغ فروش</th><th>میانگین مبلغ فروش</th><th>جزئیات</th></tr></thead><tbody id="{{ panel_prefix }}-performance-table-body"></tbody></table></div>
            </section>
        </div>
        <section id="{{ panel_prefix }}-performance-details" class="mt-5 pt-5 border-top" aria-labelledby="{{ panel_prefix }}-details-title" hidden>
            <div class="d-flex flex-wrap flex-stack align-items-center mb-4"><div><h3 id="{{ panel_prefix }}-details-title">رکوردهای پشت شاخص</h3><p id="{{ panel_prefix }}-details-scope" class="text-muted"></p></div></div>
            <div id="{{ panel_prefix }}-details-loading" class="text-center text-gray-700 py-10" hidden>در حال دریافت جزئیات…</div>
            <div id="{{ panel_prefix }}-details-error" class="text-center text-danger py-10" role="alert" hidden>جزئیات دریافت نشد.</div>
            <div id="{{ panel_prefix }}-details-empty" class="text-center text-gray-700 py-10" hidden>رکوردی برای این شاخص نیست.</div>
            <div id="{{ panel_prefix }}-details-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0"><thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>نوع</th><th>مشتری</th><th>کاربر</th><th>محصول</th><th>مبلغ</th><th>زمان</th><th>عمل</th></tr></thead><tbody id="{{ panel_prefix }}-details-body"></tbody></table></div>
            <nav id="{{ panel_prefix }}-details-pagination" class="d-flex align-items-center justify-content-between flex-wrap gap-3 mt-6 pt-4 border-top border-gray-200" aria-label="صفحه‌بندی جزئیات" hidden><button id="{{ panel_prefix }}-details-prev" class="btn btn-light" type="button">قبلی</button><span id="{{ panel_prefix }}-details-page-label"></span><button id="{{ panel_prefix }}-details-next" class="btn btn-light" type="button">بعدی</button></nav>
        </section>
    </div>
</div></section>
