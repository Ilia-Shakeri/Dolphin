{% comment %} Shared line block for Quotation, Order, and Invoice detail pages.

   The editor is rendered only for a document the backend would accept an edit
   for anyway (draft). It is display convenience, never authorisation: the
   `items` endpoint refuses a non-draft document regardless of what rendered.

   `doc` is the page prefix (quotation/order/invoice) and `endpoint` is the
   document's API base path.

   An invoice's discount is the document's (2.26.0, product-owner decision):
   one percentage in «جمع سند», not one per line — so for `doc == "invoice"`
   the lines carry no discount column and no per-line discount input, and the
   totals box holds the editable «نرخ تخفیف سند» and «نرخ مالیات». A quotation
   or an order keeps its line discounts exactly as before. {% endcomment %}
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center mb-6"><h2 class="fs-3 fw-bold text-gray-900 mb-5">اقلام سند</h2><span id="{{ doc }}-lines-count" class="text-muted"></span></div>
    <div class="table-responsive"><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0" data-line-discounts="{% if doc == "invoice" %}false{% else %}true{% endif %}">
        <thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>ردیف</th><th>کد کالا</th><th>کالا</th><th>تعداد</th><th>قیمت واحد</th>{% if doc != "invoice" %}<th>تخفیف</th>{% endif %}<th>مبلغ سطر</th><th></th></tr></thead>
        <tbody id="{{ doc }}-lines-body"></tbody>
    </table></div>
    <div id="{{ doc }}-lines-empty" class="text-center text-gray-700 py-10" hidden>این سند هنوز سطری ندارد.</div>
    <div id="{{ doc }}-lines-editor" hidden>
        <h3>افزودن سطر</h3>
        <form id="{{ doc }}-add-line-form" class="d-flex flex-wrap align-items-center gap-3 mb-5" novalidate>
            <label class="sr-only" for="{{ doc }}-line-product">کالا</label><select class="form-select form-select-solid w-auto flex-grow-1" id="{{ doc }}-line-product" name="product" required><option value="">در حال دریافت…</option></select>
            <label class="sr-only" for="{{ doc }}-line-quantity">تعداد</label><input class="form-control form-control-solid w-auto flex-grow-1" id="{{ doc }}-line-quantity" name="quantity" type="number" min="1" step="1" value="1" required placeholder="تعداد">
            <label class="sr-only" for="{{ doc }}-line-price">قیمت واحد</label><input class="form-control form-control-solid w-auto flex-grow-1" id="{{ doc }}-line-price" name="unit_price" type="text" inputmode="numeric" data-money-input dir="ltr" placeholder="قیمت واحد به {{ panel_currency_label }} (اختیاری)">
            {% if doc != "invoice" %}<label class="sr-only" for="{{ doc }}-line-discount">تخفیف سطر (٪)</label><input class="form-control form-control-solid w-auto flex-grow-1" id="{{ doc }}-line-discount" name="discount_percent" type="number" min="0" max="100" step="0.01" placeholder="تخفیف ٪">{% endif %}
            <button class="btn btn-light" type="submit">افزودن به سند</button>
        </form>
        <p class="text-muted">قیمت واحد خالی بماند، قیمت جاری کالا در همان لحظه ثبت می‌شود. تغییرات تا فشردن «ذخیره اقلام» روی سند اعمال نمی‌شود.</p>
        <div class="d-flex justify-content-end gap-3 mt-6">
            <button id="{{ doc }}-reset-lines" class="btn btn-light" type="button">بازگردانی اقلام ذخیره‌شده</button>
            <button id="{{ doc }}-save-lines" class="btn btn-primary" type="button">ذخیره اقلام</button>
        </div>
    </div>
</div></section>
{% if doc == "invoice" %}
<section class="card mb-5 mb-xl-8" id="invoice-totals-card"><div class="card-body">
    <h2 class="fs-3 fw-bold text-gray-900 mb-5">جمع سند</h2>
    <form id="invoice-totals-form" novalidate>
        <div class="row g-5">
            <div class="col-md-6"><label class="form-label fw-semibold" for="invoice-subtotal">جمع اقلام</label><input class="form-control form-control-solid" id="invoice-subtotal" disabled></div>
            <div class="col-md-6"><label class="form-label fw-semibold" for="invoice-discount-rate">نرخ تخفیف سند (٪)</label><input class="form-control form-control-solid" id="invoice-discount-rate" name="discount_percent" type="number" min="0" max="100" step="0.01" dir="ltr" disabled><p class="text-danger fs-8 mt-1 mb-0" data-error-for="discount_percent"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold" for="invoice-discount-total">تخفیف سند</label><input class="form-control form-control-solid" id="invoice-discount-total" disabled></div>
            <div class="col-md-6"><label class="form-label fw-semibold" for="invoice-tax-rate-view">نرخ مالیات (٪)</label><input class="form-control form-control-solid" id="invoice-tax-rate-view" name="tax_rate" type="number" min="0" max="100" step="0.01" dir="ltr" disabled><p class="text-danger fs-8 mt-1 mb-0" data-error-for="tax_rate"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold" for="invoice-tax-amount">مالیات</label><input class="form-control form-control-solid" id="invoice-tax-amount" disabled></div>
            {% comment %} The figure the document is about, drawn heavier than the parts
               it is made of — the theme's own light-primary state and a larger
               weight, not a colour of our own. {% endcomment %}
            <div class="col-md-6"><label class="form-label fw-bold text-primary" for="invoice-total">مبلغ نهایی</label><input class="form-control form-control-lg bg-light-primary border border-primary border-dashed text-primary fw-bolder fs-3" id="invoice-total" disabled></div>
        </div>
        <p id="invoice-legacy-line-discount" class="text-muted fs-7 mt-4 mb-0" hidden></p>
        <p id="invoice-totals-locked-note" class="text-muted fs-7 mt-4 mb-0" hidden>نرخ‌ها فقط تا وقتی فاکتور پیش‌نویس است قابل تغییرند.</p>
        <div id="invoice-totals-actions" class="d-flex justify-content-end gap-3 mt-6" hidden><button class="btn btn-primary" type="submit">ذخیره تغییرات</button></div>
    </form>
</div></section>
{% else %}
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <h2 class="fs-3 fw-bold text-gray-900 mb-5">جمع سند</h2>
    <div class="row g-5">
        <div class="col-md-6"><label class="form-label fw-semibold" for="{{ doc }}-subtotal">جمع اقلام</label><input class="form-control form-control-solid" id="{{ doc }}-subtotal" disabled></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="{{ doc }}-discount-total">تخفیف سند</label><input class="form-control form-control-solid" id="{{ doc }}-discount-total" disabled></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="{{ doc }}-tax-rate-view">نرخ مالیات (٪)</label><input class="form-control form-control-solid" id="{{ doc }}-tax-rate-view" disabled></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="{{ doc }}-tax-amount">مالیات</label><input class="form-control form-control-solid" id="{{ doc }}-tax-amount" disabled></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="{{ doc }}-total">مبلغ نهایی</label><input class="form-control form-control-solid" id="{{ doc }}-total" disabled></div>
    </div>
</div></section>
{% endif %}
