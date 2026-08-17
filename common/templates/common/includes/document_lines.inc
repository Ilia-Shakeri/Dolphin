{% comment %} Shared line block for Quotation, Order, and Invoice detail pages.

   The editor is rendered only for a document the backend would accept an edit
   for anyway (draft). It is display convenience, never authorisation: the
   `items` endpoint refuses a non-draft document regardless of what rendered.

   `doc` is the page prefix (quotation/order/invoice) and `endpoint` is the
   document's API base path. {% endcomment %}
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center mb-6"><h2>اقلام سند</h2><span id="{{ doc }}-lines-count" class="text-muted"></span></div>
    <div class="table-responsive"><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0">
        <thead><tr><th>ردیف</th><th>کد کالا</th><th>کالا</th><th>تعداد</th><th>قیمت واحد</th><th>تخفیف</th><th>مبلغ سطر</th><th></th></tr></thead>
        <tbody id="{{ doc }}-lines-body"></tbody>
    </table></div>
    <div id="{{ doc }}-lines-empty" class="text-center text-muted py-10" hidden>این سند هنوز سطری ندارد.</div>
    <div id="{{ doc }}-lines-editor" hidden>
        <h3>افزودن سطر</h3>
        <form id="{{ doc }}-add-line-form" class="d-flex flex-wrap align-items-center gap-3 mb-5" novalidate>
            <label class="sr-only" for="{{ doc }}-line-product">کالا</label><select class="form-select form-select-solid w-auto flex-grow-1" id="{{ doc }}-line-product" name="product" required><option value="">در حال دریافت…</option></select>
            <label class="sr-only" for="{{ doc }}-line-quantity">تعداد</label><input class="form-control form-control-solid w-auto flex-grow-1" id="{{ doc }}-line-quantity" name="quantity" type="number" min="1" step="1" value="1" required placeholder="تعداد">
            <label class="sr-only" for="{{ doc }}-line-price">قیمت واحد</label><input class="form-control form-control-solid w-auto flex-grow-1" id="{{ doc }}-line-price" name="unit_price" type="number" min="0" step="0.01" placeholder="قیمت واحد (اختیاری)">
            <label class="sr-only" for="{{ doc }}-line-discount">تخفیف سطر (٪)</label><input class="form-control form-control-solid w-auto flex-grow-1" id="{{ doc }}-line-discount" name="discount_percent" type="number" min="0" max="100" step="0.01" placeholder="تخفیف ٪">
            <button class="btn btn-light" type="submit">افزودن به سند</button>
        </form>
        <p class="text-muted">قیمت واحد خالی بماند، قیمت جاری کالا در همان لحظه ثبت می‌شود. تغییرات تا فشردن «ذخیره اقلام» روی سند اعمال نمی‌شود.</p>
        <div class="d-flex justify-content-end gap-3 mt-6">
            <button id="{{ doc }}-reset-lines" class="btn btn-light" type="button">بازگردانی اقلام ذخیره‌شده</button>
            <button id="{{ doc }}-save-lines" class="btn btn-primary" type="button">ذخیره اقلام</button>
        </div>
    </div>
</div></section>
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <h2>جمع سند</h2>
    <div class="row g-5">
        <div class="col-md-6"><label class="form-label fw-semibold" for="{{ doc }}-subtotal">جمع اقلام</label><input class="form-control form-control-solid" id="{{ doc }}-subtotal" disabled></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="{{ doc }}-discount-total">تخفیف سند</label><input class="form-control form-control-solid" id="{{ doc }}-discount-total" disabled></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="{{ doc }}-tax-rate-view">نرخ مالیات (٪)</label><input class="form-control form-control-solid" id="{{ doc }}-tax-rate-view" disabled></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="{{ doc }}-tax-amount">مالیات</label><input class="form-control form-control-solid" id="{{ doc }}-tax-amount" disabled></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="{{ doc }}-total">مبلغ نهایی</label><input class="form-control form-control-solid" id="{{ doc }}-total" disabled></div>
    </div>
</div></section>
