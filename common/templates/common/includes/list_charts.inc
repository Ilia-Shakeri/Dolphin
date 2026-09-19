{% comment %} دو نمودار زیر هر فهرست، هر دو از یک پاسخ
   (`/api/v1/reports/list-chart/<key>/`). داده‌شان از همان selector ماژول می‌آید
   که جدول بالا از آن می‌خواند، پس هرگز بیشتر از دامنهٔ دسترسی کاربر نشان
   نمی‌دهند. اگر نقش یا استقرار به آن دسترسی نداشته باشد، فقط همین کارت پیام
   می‌دهد و بقیهٔ صفحه دست‌نخورده کار می‌کند.

   چپ: «از چه چیزهایی تشکیل شده» (حلقه یا میله). راست: «به کدام سمت می‌رود»
   (روند دوازده هفتهٔ اخیر) — درخواست مالک محصول ۲۰۲۶/۰۹/۱۹. یک کارت واحد است
   که در یازده صفحهٔ فهرست include می‌شود، نه یازده نسخهٔ کپی‌شده. {% endcomment %}
<section class="card mb-5 mb-xl-8" data-list-chart="{{ chart_key }}"><div class="card-body">
    <div class="row g-8">
        <div class="col-xl-6">
            <div class="d-flex flex-wrap flex-stack align-items-center mb-4">
                <h2 class="fs-3 fw-bold text-gray-900 mb-0" data-list-chart-title>نمودار</h2>
            </div>
            <div class="performance-chart" data-list-chart-canvas role="img" aria-label="نمودار این فهرست" hidden></div>
            <p class="text-center text-gray-700 py-10" data-list-chart-empty hidden>داده‌ای برای نمایش نیست.</p>
        </div>
        <div class="col-xl-6" data-list-trend hidden>
            <div class="d-flex flex-wrap flex-stack align-items-center mb-4">
                <h2 class="fs-3 fw-bold text-gray-900 mb-0" data-list-trend-title>روند</h2>
            </div>
            <div class="performance-chart" data-list-trend-canvas role="img" aria-label="روند این فهرست" hidden></div>
            <p class="text-center text-gray-700 py-10" data-list-trend-empty hidden>داده‌ای برای نمایش نیست.</p>
        </div>
    </div>
</div></section>
