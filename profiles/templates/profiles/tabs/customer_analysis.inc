{% comment %} تحلیل مشتری (۲.۳۳.۰): پنج باکس کوچک و زیر آن یک نمودار خطیِ نرم؛
   عنوان هر باکس را بزنید تا نمودار همان شاخص را نشان دهد. اعداد و سری‌ها از
   `/api/v1/profiles/customer/<id>/analysis/` می‌آیند که دامنهٔ کاربر را خودش
   می‌سنجد؛ شاخصی که کاربر حق دیدنش را ندارد «—» با دلیل است، نه صفر. {% endcomment %}
<section id="customer-analysis" aria-label="تحلیل مشتری">
    <div id="customer-analysis-error" class="text-center text-danger py-6" role="alert" hidden>تحلیل دریافت نشد.</div>
    <div class="row g-5 g-xl-8 mb-5 mb-xl-8" id="customer-analysis-kpis">
        {% for key, title in analysis_kpis %}
        <div class="col-sm-6 col-xl">
            <button class="card card-flush h-100 w-100 text-start border border-dashed border-gray-300 bg-body" type="button" data-analysis-kpi="{{ key }}" aria-pressed="false">
                <span class="card-body d-flex flex-column justify-content-between p-6">
                    <span class="fs-6 fw-semibold text-gray-600 mb-3" data-analysis-title>{{ title }}</span>
                    <span class="fs-2 fw-bolder text-gray-900 lh-1" data-analysis-value>—</span>
                </span>
            </button>
        </div>
        {% endfor %}
    </div>
    <section class="card mb-5 mb-xl-8"><div class="card-body">
        <h2 class="fs-3 fw-bold text-gray-900 mb-1" id="customer-analysis-chart-title">نمودار</h2>
        <p class="text-muted fs-7 mb-5" id="customer-analysis-chart-note">یکی از باکس‌های بالا را انتخاب کنید.</p>
        <div id="customer-analysis-chart" role="img" aria-label="نمودار تحلیل مشتری" hidden></div>
        <p id="customer-analysis-chart-empty" class="text-center text-gray-700 py-10">در حال دریافت تحلیل…</p>
    </div></section>
</section>
