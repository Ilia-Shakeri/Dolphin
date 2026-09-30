import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money, moneyOrNull} from "dolphin/core/money.js";
import {fillSelect, loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {setupSearchableSelects} from "dolphin/ui/searchable-select.js";
import {appendCell, appendDetailLink, appendMoneyCell} from "dolphin/ui/table.js";

export const PAYMENT_METHOD_TEXT = Object.freeze({
    cash: "نقدی",
    card: "کارت‌خوان",
    bank_transfer: "حواله بانکی",
    cheque: "چک",
});

export const CHEQUE_STATUS_TEXT = Object.freeze({
    pending: "در انتظار",
    cleared: "وصول شده",
    bounced: "برگشت",
    spent: "خرج شده",
});
export const CHEQUE_REGISTRATION_TEXT = Object.freeze({
    true: "ثبت شده",
    false: "ثبت نشده",
});
export const INSTALLMENT_DISPLAY_ACCENT = Object.freeze({
    paid: "success",
    cancelled: "danger",
    partially_paid: "warning",
    near_due: "info",
    due_today: "warning",
    overdue: "danger",
    pending: "secondary",
});

export function numberOrNull(value) {
    const text = String(value ?? "").trim();
    return text === "" ? null : Number(text);
}

export async function loadCustomerOptions(select, emptyLabel) {
    if (!select) return [];
    const rows = await loadAllPages("/api/v1/customers/?ordering=full_name");
    fillSelect(select, rows, (row) => row.full_name, emptyLabel);
    return rows;
}

// --- Commercial documents -----------------------------------------------

function documentListRow(document_, columns, href) {
    const row = document.createElement("tr");
    columns.forEach((render) => render(row, document_));
    appendDetailLink(row, href(document_));
    return row;
}

export function setupDocumentList({key, prefix, endpoint, columns, detailPath, createFields, onOpen}) {
    const form = document.getElementById(`${prefix}-search-form`);
    setupListFilter(prefix);
    const dialog = document.getElementById(`create-${prefix}-dialog`);
    let controller = null;
    if (dialog) {
        const createForm = document.getElementById(`create-${prefix}-form`);
        document.getElementById(`open-create-${prefix}`).addEventListener("click", () => {
            onOpen?.();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const created = await apiRequest(createForm.action, {
                    method: "POST",
                    body: createFields(new FormData(createForm)),
                });
                window.location.assign(`${detailPath}${created.id}/`);
            });
        });
    }
    controller = setupPagedList({
        key,
        form,
        search: document.getElementById(`${prefix}-search`),
        endpoint,
        renderRow: (row) => documentListRow(row, columns, (item) => `${detailPath}${item.id}/`),
    });
    controller.load();
    return controller;
}

/**
 * One dynamic line of a document, shared by the invoice and order
 * creation wizards.
 *
 * Until 2.12.0 a line was a product picker, a quantity box and a delete
 * button, and that was all a reader saw until the review step: no price,
 * no line total, and no idea what the document would come to. The product
 * owner asked for this step to be redone — «فاصله‌گذاری حرفه‌ای، اندازهٔ
 * مناسب فیلدها و ستون‌ها، ترازبندی اعداد، رفتار درست در موبایل، اعتبارسنجی
 * و پیام خطای واضح» (2026-09-20) — and the numbers to align are the ones
 * that were missing.
 *
 * `host` is the container the rows live in; `products` is the shared
 * catalogue the caller already fetched once, whose rows carry
 * `current_price`. `onChange` fires whenever anything that affects a
 * total changes, so the caller can redraw its summary.
 *
 * The price is shown, not edited. The API accepts a per-line
 * `unit_price`, but the wizard has never sent one and the server uses the
 * product's own current price — showing an editable box here would offer
 * an override this form does not actually make.
 */
export function createLineItemRows(host, products, {onChange} = {}) {
    const byId = new Map(products.map((item) => [Number(item.id), item]));
    const notify = () => { if (onChange) onChange(); };

    function addLine() {
        if (!host) return;
        const row = document.createElement("div");
        // A grid, not a wrapping flex row. Flex wrapping put each control
        // on its own line at an unpredictable width, so the single header
        // above the rows named columns that were no longer under it; the
        // grid keeps the same five tracks on every row and collapses to
        // one labelled column on a phone (see `.wizard-line-row` in §7a).
        row.className = "wizard-line-row";
        row.dataset.lineRow = "";

        const picker = document.createElement("div");
        picker.className = "searchable-select wizard-line-product";
        picker.setAttribute("data-searchable-select", "");
        const search = document.createElement("input");
        search.className = "form-control form-control-solid";
        search.type = "search";
        search.autocomplete = "off";
        search.placeholder = "نام یا کد کالا…";
        search.setAttribute("data-searchable-input", "");
        search.setAttribute("role", "combobox");
        search.setAttribute("aria-label", "جستجوی کالا");
        search.hidden = true;
        const select = document.createElement("select");
        select.className = "form-select form-select-solid";
        select.dataset.lineProduct = "";
        select.setAttribute("data-searchable-source", "");
        select.setAttribute("aria-label", "کالا");
        // Required, so the wizard's own `:invalid` gate refuses to leave
        // this step with an empty row and the browser says why, in the
        // reader's own language, without a second rule written here.
        select.required = true;
        fillSelect(select, products, (item) => `${item.name} (${item.sku})`, "یک کالا انتخاب کنید");
        const options = document.createElement("ul");
        options.className = "searchable-select-options";
        options.setAttribute("role", "listbox");
        options.hidden = true;
        picker.append(search, select, options);

        const price = document.createElement("div");
        price.className = "wizard-line-price";
        price.dataset.linePrice = "";
        // On a phone the header row is gone and each cell carries its own
        // label through `::before` (see the `md` block in §7a).
        price.dataset.label = "قیمت واحد";

        const quantity = document.createElement("input");
        quantity.className = "form-control form-control-solid wizard-line-quantity";
        quantity.type = "number";
        quantity.min = "1";
        // `clean_quantity`'s own ceiling (billing/money.py). Stated here so
        // the browser refuses it before the request rather than after.
        quantity.max = "1000000";
        quantity.step = "1";
        quantity.value = "1";
        quantity.required = true;
        quantity.dataset.lineQuantity = "";
        quantity.setAttribute("aria-label", "تعداد");

        const total = document.createElement("div");
        total.className = "wizard-line-total";
        total.dataset.lineTotal = "";
        total.dataset.label = "جمع ردیف";

        const remove = document.createElement("button");
        // The theme's own repeater delete control, icon and all — a real
        // `di-cross` rather than a literal "×" character, which rendered
        // at text weight beside two solid inputs.
        remove.className = "btn btn-sm btn-icon btn-light-danger wizard-line-remove";
        remove.type = "button";
        const removeIcon = document.createElement("i");
        removeIcon.className = "di-duotone di-cross fs-2";
        ["path1", "path2"].forEach((name) => {
            const path = document.createElement("span");
            path.className = name;
            removeIcon.append(path);
        });
        remove.append(removeIcon);
        remove.setAttribute("aria-label", "حذف ردیف");
        remove.addEventListener("click", () => {
            row.remove();
            // Never none: a document without a line cannot be submitted,
            // so the form always offers one to fill.
            if (!host.children.length) addLine();
            else notify();
        });

        function repaint() {
            const product = byId.get(Number(select.value));
            const unit = product ? Number(product.current_price) : null;
            price.textContent = unit === null ? "—" : money(unit);
            const count = Number(quantity.value);
            total.textContent = unit === null || !(count > 0)
                ? "—"
                : money(unit * count);
            notify();
        }
        select.addEventListener("change", repaint);
        quantity.addEventListener("input", repaint);

        row.append(picker, price, quantity, total, remove);
        host.append(row);
        setupSearchableSelects(row);
        repaint();
    }

    function reset() {
        if (!host) return;
        host.innerHTML = "";
        addLine();
    }

    function collect() {
        if (!host) return [];
        return [...host.querySelectorAll("[data-line-row]")]
            .map((row) => ({
                product: Number(row.querySelector("[data-line-product]").value),
                quantity: Number(row.querySelector("[data-line-quantity]").value),
            }))
            .filter((line) => line.product && line.quantity > 0);
    }

    /**
     * The gross amount of every usable line, for a running total.
     *
     * Money is rounded the way `billing/money.py` rounds it — half up, to
     * two places — so the figure under the form is the figure the server
     * will store rather than one that differs by a rial and makes the
     * reader doubt both.
     */
    function grossTotals() {
        return collect().map((line) => {
            const product = byId.get(line.product);
            const unit = product ? Number(product.current_price) : 0;
            return roundMoney(unit * line.quantity);
        });
    }

    /** The first product chosen twice, or `null`. */
    function duplicateProduct() {
        const seen = new Set();
        for (const line of collect()) {
            if (seen.has(line.product)) return byId.get(line.product) || null;
            seen.add(line.product);
        }
        return null;
    }

    return {addLine, reset, collect, grossTotals, duplicateProduct, count: () => collect().length};
}

//: What a wizard holds before its catalogue has loaded. A real object
//: rather than a `null` check at each of the dozen call sites, and one
//: object rather than a fresh literal per wizard.
export const EMPTY_LINE_ROWS = Object.freeze({
    addLine() {},
    reset() {},
    collect: () => [],
    grossTotals: () => [],
    duplicateProduct: () => null,
    count: () => 0,
});

//: The server's own ceiling on how many lines one document may carry
//: (`BILLING_MAX_DOCUMENT_ITEMS`, default 200). Stated so the wizard can
//: refuse before the request rather than after; the server still
//: enforces it, and a deployment that lowers the setting simply gets a
//: server-side refusal here instead of a local one.
const MAX_DOCUMENT_LINES = 200;

/**
 * What the markup itself cannot say about a lines step.
 *
 * The wizard's own `:invalid` gate already covers "a row with no product
 * chosen" and "a quantity below one" — both are `required` attributes on
 * the controls, and the browser writes the sentence. Two rules are left
 * that no attribute can express, and both are real: the same product on
 * two rows becomes two line items for one thing, and a document past the
 * server's line ceiling is refused after the reader has filled it in.
 */
export function validateLinesStep(content, lines) {
    if (!content || !content.classList.contains("wizard-lines-step")) return null;
    const duplicate = lines.duplicateProduct();
    if (duplicate) {
        return `«${duplicate.name}» در دو ردیف انتخاب شده است. تعداد را در یک ردیف جمع کنید یا ردیف تکراری را حذف کنید.`;
    }
    if (lines.count() > MAX_DOCUMENT_LINES) {
        return `یک سند حداکثر ${toPersianDigits(String(MAX_DOCUMENT_LINES))} ردیف می‌تواند داشته باشد؛ اکنون ${toPersianDigits(String(lines.count()))} ردیف دارد.`;
    }
    return null;
}

/** Two decimal places, rounded half up — `billing.money.quantize_money`. */
function roundMoney(value) {
    return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
}

/**
 * What a document will come to, computed the way the server computes it.
 *
 * Since 2.26.0 the discount is the document's, one percentage of the
 * summed lines (`Invoice.discount_percent`, `billing.money.document_totals`),
 * not one per line: sum the lines, take the discount off the sum, and
 * charge the tax on what is left. Same order, same rounding at each step
 * as the server, so the figure here is the figure that is saved.
 */
export function documentTotals(grossLines, discountPercent, taxRate) {
    const percent = Math.min(Math.max(Number(discountPercent) || 0, 0), 100);
    const rate = Math.min(Math.max(Number(taxRate) || 0, 0), 100);
    const gross = grossLines.reduce((sum, line) => roundMoney(sum + line), 0);
    const discount = roundMoney((gross * percent) / 100);
    const subtotal = roundMoney(gross - discount);
    const tax = roundMoney((subtotal * rate) / 100);
    return {gross, discount, subtotal, tax, total: roundMoney(subtotal + tax)};
}

/**
 * Draw a wizard's running totals into its own summary block.
 *
 * One function for both wizards: the invoice and the order steps are the
 * same four figures over the same arithmetic, and two copies is how they
 * would come to disagree.
 */
export function renderDocumentTotals(prefix, lines) {
    const host = document.getElementById(`${prefix}-totals`);
    if (!host) return;
    const discountField = document.getElementById(`${prefix}-discount`);
    const taxField = document.getElementById(`${prefix}-tax`);
    const totals = documentTotals(
        lines.grossTotals(),
        discountField ? discountField.value : 0,
        taxField ? taxField.value : 0,
    );
    const set = (name, value) => {
        const cell = host.querySelector(`[data-total="${name}"]`);
        if (cell) cell.textContent = money(value);
    };
    set("gross", totals.gross);
    set("discount", totals.discount);
    set("tax", totals.tax);
    set("total", totals.total);
    const count = host.querySelector("[data-total=\"count\"]");
    if (count) count.textContent = toPersianDigits(String(lines.count()));
}

/** Shared line editor and totals for one commercial document.
 *
 * Lines are edited as one local list and written back with a single call to
 * the document's `items` endpoint, which replaces the whole set. That keeps
 * the stored header totals and the stored lines from ever disagreeing —
 * the service recomputes the totals from the lines it just wrote.
 */
export function documentLineEditor({doc, endpoint, onSaved}) {
    const body = document.getElementById(`${doc}-lines-body`);
    const empty = document.getElementById(`${doc}-lines-empty`);
    const editor = document.getElementById(`${doc}-lines-editor`);
    const countLabel = document.getElementById(`${doc}-lines-count`);
    const addForm = document.getElementById(`${doc}-add-line-form`);
    const saveButton = document.getElementById(`${doc}-save-lines`);
    const resetButton = document.getElementById(`${doc}-reset-lines`);
    const productSelect = document.getElementById(`${doc}-line-product`);
    // Whether this document's lines carry their own discount. An
    // invoice's does not (2.26.0): its discount is the document's, in
    // «جمع سند»; the template says which by `data-line-discounts`.
    const lineDiscounts = body?.closest("table")?.dataset.lineDiscounts !== "false";
    // The invoice's editable rates, when the template drew them.
    const totalsForm = document.getElementById(`${doc}-totals-form`);
    let stored = [];
    let draft = [];
    let editable = false;
    let products = [];

    function productLabel(id) {
        const match = products.find((item) => item.id === Number(id));
        return match ? `${match.name} (${match.sku})` : String(id);
    }

    function render() {
        const rows = draft.map((line, index) => {
            const row = document.createElement("tr");
            appendCell(row, index + 1);
            appendCell(row, line.product_sku_snapshot || "—").dir = "ltr";
            appendCell(row, line.product_name_snapshot || productLabel(line.product));
            appendCell(row, line.quantity);
            appendMoneyCell(row, line.unit_price);
            if (lineDiscounts) appendMoneyCell(row, line.discount_amount);
            appendMoneyCell(row, line.line_total);
            const actions = document.createElement("td");
            actions.className = "row-actions";
            if (editable) {
                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "btn btn-sm btn-light";
                remove.textContent = "حذف سطر";
                remove.addEventListener("click", () => {
                    draft.splice(index, 1);
                    render();
                });
                actions.appendChild(remove);
            }
            row.appendChild(actions);
            return row;
        });
        body.replaceChildren(...rows);
        empty.hidden = draft.length > 0;
        countLabel.textContent = draft.length ? `${draft.length} سطر` : "";
    }

    addForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        const data = new FormData(addForm);
        const product = numberOrNull(data.get("product"));
        const quantity = numberOrNull(data.get("quantity"));
        if (product === null || quantity === null || quantity < 1) {
            globalMessage("کالا و تعداد سطر را کامل وارد کنید.");
            return;
        }
        const unitPrice = moneyOrNull(data.get("unit_price"));
        const discountPercent = numberOrNull(data.get("discount_percent"));
        const match = products.find((item) => item.id === product);
        const price = unitPrice === null ? Number(match ? match.current_price : 0) : Number(unitPrice);
        const gross = price * quantity;
        const discount = discountPercent ? (gross * discountPercent) / 100 : 0;
        draft.push({
            product,
            quantity,
            unit_price: unitPrice,
            discount_percent: discountPercent,
            // Preview only. The server recomputes every amount from the
            // product price it reads at write time, and its numbers win.
            product_name_snapshot: match ? match.name : "",
            product_sku_snapshot: match ? match.sku : "",
            line_total: (gross - discount).toFixed(2),
            discount_amount: discount.toFixed(2),
        });
        addForm.reset();
        document.getElementById(`${doc}-line-quantity`).value = "1";
        render();
    });

    resetButton?.addEventListener("click", () => {
        draft = stored.map((line) => ({...line}));
        render();
        globalMessage("اقلام ذخیره‌شده بازگردانده شد.", true);
    });

    saveButton?.addEventListener("click", async () => {
        if (!draft.length) {
            globalMessage("سند باید دست‌کم یک سطر داشته باشد.");
            return;
        }
        saveButton.disabled = true;
        clearMessages();
        try {
            const payload = draft.map((line) => {
                const item = {product: Number(line.product), quantity: Number(line.quantity)};
                if (line.unit_price !== null && line.unit_price !== undefined) {
                    item.unit_price = String(line.unit_price);
                }
                if (line.discount_percent) item.discount_percent = String(line.discount_percent);
                return item;
            });
            const updated = await apiRequest(`${endpoint}items/`, {method: "POST", body: {items: payload}});
            globalMessage("اقلام سند ذخیره شد.", true);
            onSaved(updated);
        } catch (error) {
            showError(error);
        } finally {
            saveButton.disabled = false;
        }
    });

    // «ذخیره تغییرات» under «جمع سند»: the document's discount rate and
    // tax rate, sent together. The service recomputes every amount from
    // the stored lines and refuses anything but a draft.
    totalsForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(totalsForm, async () => {
            const rate = (id) => {
                const raw = String(document.getElementById(id).value || "").trim();
                return raw === "" ? "0" : raw;
            };
            const updated = await apiRequest(endpoint, {
                method: "PATCH",
                body: {
                    discount_percent: rate(`${doc}-discount-rate`),
                    tax_rate: rate(`${doc}-tax-rate-view`),
                },
            });
            globalMessage("نرخ‌های سند ذخیره شد.", true);
            onSaved(updated);
        });
    });

    function applyTotalsForm(document_) {
        const discountRate = document.getElementById(`${doc}-discount-rate`);
        const taxRate = document.getElementById(`${doc}-tax-rate-view`);
        // The rate the operator gave at creation. An invoice from before
        // 2.26.0 carries its discount as an amount only; its rate is shown
        // as that amount's share of the subtotal, and saving turns it into
        // a percentage.
        let percent = document_.discount_percent;
        if (percent === null || percent === undefined) {
            const subtotal = Number(document_.subtotal_amount) || 0;
            const discount = Number(document_.discount_amount) || 0;
            percent = subtotal > 0 ? roundMoney((discount * 100) / subtotal) : 0;
        }
        discountRate.value = String(Number(percent));
        taxRate.value = String(Number(document_.tax_rate));
        discountRate.disabled = !editable;
        taxRate.disabled = !editable;
        document.getElementById(`${doc}-totals-actions`).hidden = !editable;
        document.getElementById(`${doc}-totals-locked-note`).hidden = editable;
        // Discounts that older invoices put on each line are part of their
        // line totals already; with the column gone, say so once here.
        const legacy = (document_.line_items || [])
            .reduce((sum, line) => sum + (Number(line.discount_amount) || 0), 0);
        const legacyNote = document.getElementById(`${doc}-legacy-line-discount`);
        legacyNote.hidden = legacy <= 0;
        legacyNote.textContent = legacy > 0
            ? `این فاکتور پیش از تخفیفِ سندی ثبت شده و ${money(legacy)} تخفیف ردیفی در مبلغ سطرهایش لحاظ شده است.`
            : "";
    }

    return {
        async loadProducts() {
            products = await loadAllPages("/api/v1/products/?is_active=true&ordering=name");
            if (productSelect) {
                fillSelect(productSelect, products, (item) => `${item.name} (${item.sku})`, "یک کالا انتخاب کنید");
            }
        },
        apply(document_) {
            stored = (document_.line_items || []).map((line) => ({
                product: line.product,
                quantity: line.quantity,
                unit_price: line.unit_price,
                discount_percent: Number(line.discount_percent) || null,
                discount_amount: line.discount_amount,
                line_total: line.line_total,
                product_name_snapshot: line.product_name_snapshot,
                product_sku_snapshot: line.product_sku_snapshot,
            }));
            draft = stored.map((line) => ({...line}));
            editable = document_.status === "draft";
            if (editor) editor.hidden = !editable;
            render();
            document.getElementById(`${doc}-subtotal`).value = money(document_.subtotal_amount);
            document.getElementById(`${doc}-discount-total`).value = money(document_.discount_amount);
            document.getElementById(`${doc}-tax-rate-view`).value = document_.tax_rate;
            document.getElementById(`${doc}-tax-amount`).value = money(document_.tax_amount);
            document.getElementById(`${doc}-total`).value = money(document_.total_amount);
            if (totalsForm) applyTotalsForm(document_);
        },
    };
}

// --- Financial reports ---------------------------------------------------

export function reportSection(prefix) {
    return {
        loading: document.getElementById(`${prefix}-loading`),
        empty: document.getElementById(`${prefix}-empty`),
        wrap: document.getElementById(`${prefix}-table-wrap`),
        body: document.getElementById(`${prefix}-table-body`),
    };
}

export function renderReportRows(prefix, rows, renderRow) {
    const nodes = reportSection(prefix);
    nodes.body.replaceChildren(...rows.map(renderRow));
    nodes.loading.hidden = true;
    nodes.empty.hidden = rows.length > 0;
    nodes.wrap.hidden = rows.length === 0;
}
