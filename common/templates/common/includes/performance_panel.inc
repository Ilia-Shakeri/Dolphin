<section class="card performance-panel" data-performance-panel="{{ panel_prefix }}" data-company-scope="{{ can_view_company_reports|yesno:'true,false' }}" aria-labelledby="{{ panel_prefix }}-performance-title">
    <div class="section-head">
        <div>
            <h2 id="{{ panel_prefix }}-performance-title">{% if can_view_company_reports %}عملکرد عملیاتی شرکت{% else %}عملکرد عملیاتی من{% endif %}</h2>
            <p class="muted">مشتری‌های ثبت‌شده و فروش‌های تأییدشده در بازه انتخابی.</p>
        </div>
    </div>
    <form id="{{ panel_prefix }}-performance-filter-form" class="performance-filter" action="/api/v1/reports/user-performance/" method="get" novalidate>
        <div class="form-grid performance-filter-grid">
            <div><label for="{{ panel_prefix }}-period-start">شروع بازه</label><input id="{{ panel_prefix }}-period-start" name="period_start" type="datetime-local" required><p class="field-error" data-error-for="period_start"></p></div>
            <div><label for="{{ panel_prefix }}-period-end">پایان بازه</label><input id="{{ panel_prefix }}-period-end" name="period_end" type="datetime-local" required><p class="field-error" data-error-for="period_end"></p></div>
            {% if can_view_company_reports %}<div><label for="{{ panel_prefix }}-user">کاربر</label><select id="{{ panel_prefix }}-user" name="user_id"><option value="">همه کاربران مجاز</option></select><p class="field-error" data-error-for="user_id"></p></div>{% endif %}
            <div><label for="{{ panel_prefix }}-product">محصول فروش</label><select id="{{ panel_prefix }}-product" name="sales_product_id"><option value="">همه محصولات مجاز</option></select><p class="muted field-hint">این فیلتر فقط شاخص‌های فروش را تغییر می‌دهد.</p><p class="field-error" data-error-for="sales_product_id"></p></div>
            <div class="form-actions"><a id="{{ panel_prefix }}-performance-xlsx" class="button button-muted" href="/api/v1/exports/user-performance.xlsx" download>دریافت XLSX</a><button class="button" type="submit">به‌روزرسانی</button></div>
        </div>
    </form>
    <div id="{{ panel_prefix }}-performance-loading" class="state" hidden>در حال دریافت عملکرد…</div>
    <div id="{{ panel_prefix }}-performance-error" class="state state-error" role="alert" hidden>گزارش دریافت نشد. دوباره تلاش کنید.</div>
    <div id="{{ panel_prefix }}-performance-empty" class="state" hidden>در این بازه مشتری تازه یا فروش تأییدشده‌ای ثبت نشده است.</div>
    <div id="{{ panel_prefix }}-performance-content" hidden>
        <div class="metric-grid performance-kpis" aria-label="شاخص‌های قطعی عملکرد">
            <div class="metric"><span>مشتری ثبت‌شده</span><strong data-kpi="customers_created_count">۰</strong></div>
            <div class="metric"><span>تعداد فروش تأییدشده</span><strong data-kpi="sales_count">۰</strong></div>
            <div class="metric"><span>مبلغ فروش تأییدشده</span><strong data-kpi="sales_amount">۰.۰۰</strong></div>
            <div class="metric"><span>میانگین مبلغ فروش تأییدشده</span><strong data-kpi="average_sale_amount">۰.۰۰</strong></div>
        </div>
        <div class="row-actions performance-summary-actions">
            <button class="button button-muted" type="button" data-performance-detail="customers_created_count">مشتری‌های پشت این جمع</button>
            <button class="button button-muted" type="button" data-performance-detail="sales_count">فروش‌های پشت این جمع</button>
        </div>
        <div class="performance-layout">
            <section class="performance-chart-card" aria-labelledby="{{ panel_prefix }}-chart-title">
                <h3 id="{{ panel_prefix }}-chart-title">مبلغ فروش تأییدشده به تفکیک کاربر</h3>
                <div id="{{ panel_prefix }}-performance-chart" class="performance-chart" role="img" aria-label="نمودار مبلغ فروش تأییدشده کاربران مجاز"></div>
                <p id="{{ panel_prefix }}-performance-chart-empty" class="state" hidden>فروش تأییدشده‌ای برای نمودار نیست.</p>
            </section>
            <section class="performance-table-card" aria-labelledby="{{ panel_prefix }}-table-title">
                <h3 id="{{ panel_prefix }}-table-title">جزئیات همان محدوده مجاز</h3>
                <div class="table-wrap"><table><thead><tr><th>کاربر</th><th>مشتری ثبت‌شده</th><th>فروش تأییدشده</th><th>مبلغ فروش</th><th>میانگین مبلغ فروش</th><th>جزئیات</th></tr></thead><tbody id="{{ panel_prefix }}-performance-table-body"></tbody></table></div>
            </section>
        </div>
        <section id="{{ panel_prefix }}-performance-details" class="performance-details" aria-labelledby="{{ panel_prefix }}-details-title" hidden>
            <div class="section-head"><div><h3 id="{{ panel_prefix }}-details-title">رکوردهای پشت شاخص</h3><p id="{{ panel_prefix }}-details-scope" class="muted"></p></div></div>
            <div id="{{ panel_prefix }}-details-loading" class="state" hidden>در حال دریافت جزئیات…</div>
            <div id="{{ panel_prefix }}-details-error" class="state state-error" role="alert" hidden>جزئیات دریافت نشد.</div>
            <div id="{{ panel_prefix }}-details-empty" class="state" hidden>رکوردی برای این شاخص نیست.</div>
            <div id="{{ panel_prefix }}-details-table-wrap" class="table-wrap" hidden><table><thead><tr><th>نوع</th><th>مشتری</th><th>کاربر</th><th>محصول</th><th>مبلغ</th><th>زمان</th><th>عمل</th></tr></thead><tbody id="{{ panel_prefix }}-details-body"></tbody></table></div>
            <nav id="{{ panel_prefix }}-details-pagination" class="pagination" aria-label="صفحه‌بندی جزئیات" hidden><button id="{{ panel_prefix }}-details-prev" class="button button-muted" type="button">قبلی</button><span id="{{ panel_prefix }}-details-page-label"></span><button id="{{ panel_prefix }}-details-next" class="button button-muted" type="button">بعدی</button></nav>
        </section>
    </div>
</section>
