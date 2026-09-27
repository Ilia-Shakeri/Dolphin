{% comment %} فاکتورهای این مشتری: هر سطر یک سند — شماره، وضعیت، مبلغ، مانده —
   و خودِ سند یک کلیک آن‌طرف‌تر در ماژول فاکتورها باز می‌شود. این زبانه فقط برای
   کسی رندر می‌شود که ویژگی و اختیار فاکتور دارد؛ نقطهٔ انتهایی مستقل از این
   نشانه‌گذاری هم دامنه را بررسی می‌کند. {% endcomment %}
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center gap-3 mb-4">
        <h2 class="fs-3 fw-bold text-gray-900 mb-0">فاکتورهای مرتبط</h2>
        {% if "customer_ledger" in features and can_view_ledger %}<a class="btn btn-sm btn-light" href="{% url 'common_ui:customer-ledger' %}?customer={{ customer_id }}">دفتر حساب این مشتری</a>{% endif %}
    </div>
    <div id="customer-invoices-loading" class="text-center text-gray-700 py-10">در حال دریافت فاکتورها…</div><div id="customer-invoices-empty" class="text-center text-gray-700 py-10" hidden>فاکتوری برای این مشتری در محدوده دسترسی شما نیست.</div>
    <div id="customer-invoices-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0"><thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>شماره</th><th>وضعیت</th><th>تسویه</th><th>مبلغ کل</th><th>مانده</th><th>تاریخ صدور</th><th>عملیات</th></tr></thead><tbody id="customer-invoices-table-body"></tbody></table></div>
    <nav id="customer-invoices-pagination" class="d-flex align-items-center justify-content-between flex-wrap gap-3 mt-6 pt-4 border-top border-gray-200" aria-label="صفحه‌بندی فاکتورهای مرتبط" hidden><button id="customer-invoices-prev" class="btn btn-light" type="button">قبلی</button><span id="customer-invoices-page-label"></span><button id="customer-invoices-next" class="btn btn-light" type="button">بعدی</button></nav>
</div></section>
