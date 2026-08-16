{% comment %} Shared line block for Quotation, Order, and Invoice detail pages.

   The editor is rendered only for a document the backend would accept an edit
   for anyway (draft). It is display convenience, never authorisation: the
   `items` endpoint refuses a non-draft document regardless of what rendered.

   `doc` is the page prefix (quotation/order/invoice) and `endpoint` is the
   document's API base path. {% endcomment %}
<section class="card">
    <div class="page-head"><h2>اقلام سند</h2><span id="{{ doc }}-lines-count" class="muted"></span></div>
    <div class="table-wrap"><table>
        <thead><tr><th>ردیف</th><th>کد کالا</th><th>کالا</th><th>تعداد</th><th>قیمت واحد</th><th>تخفیف</th><th>مبلغ سطر</th><th></th></tr></thead>
        <tbody id="{{ doc }}-lines-body"></tbody>
    </table></div>
    <div id="{{ doc }}-lines-empty" class="state" hidden>این سند هنوز سطری ندارد.</div>
    <div id="{{ doc }}-lines-editor" hidden>
        <h3>افزودن سطر</h3>
        <form id="{{ doc }}-add-line-form" class="toolbar" novalidate>
            <label class="sr-only" for="{{ doc }}-line-product">کالا</label><select id="{{ doc }}-line-product" name="product" required><option value="">در حال دریافت…</option></select>
            <label class="sr-only" for="{{ doc }}-line-quantity">تعداد</label><input id="{{ doc }}-line-quantity" name="quantity" type="number" min="1" step="1" value="1" required placeholder="تعداد">
            <label class="sr-only" for="{{ doc }}-line-price">قیمت واحد</label><input id="{{ doc }}-line-price" name="unit_price" type="number" min="0" step="0.01" placeholder="قیمت واحد (اختیاری)">
            <label class="sr-only" for="{{ doc }}-line-discount">تخفیف سطر (٪)</label><input id="{{ doc }}-line-discount" name="discount_percent" type="number" min="0" max="100" step="0.01" placeholder="تخفیف ٪">
            <button class="button button-muted" type="submit">افزودن به سند</button>
        </form>
        <p class="muted">قیمت واحد خالی بماند، قیمت جاری کالا در همان لحظه ثبت می‌شود. تغییرات تا فشردن «ذخیره اقلام» روی سند اعمال نمی‌شود.</p>
        <div class="form-actions">
            <button id="{{ doc }}-reset-lines" class="button button-muted" type="button">بازگردانی اقلام ذخیره‌شده</button>
            <button id="{{ doc }}-save-lines" class="button" type="button">ذخیره اقلام</button>
        </div>
    </div>
</section>
<section class="card">
    <h2>جمع سند</h2>
    <div class="form-grid readonly-grid">
        <div><label for="{{ doc }}-subtotal">جمع اقلام</label><input id="{{ doc }}-subtotal" disabled></div>
        <div><label for="{{ doc }}-discount-total">تخفیف سند</label><input id="{{ doc }}-discount-total" disabled></div>
        <div><label for="{{ doc }}-tax-rate-view">نرخ مالیات (٪)</label><input id="{{ doc }}-tax-rate-view" disabled></div>
        <div><label for="{{ doc }}-tax-amount">مالیات</label><input id="{{ doc }}-tax-amount" disabled></div>
        <div><label for="{{ doc }}-total">مبلغ نهایی</label><input id="{{ doc }}-total" disabled></div>
    </div>
</section>
