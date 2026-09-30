import {apiRequest} from "dolphin/core/api.js";
import {CURRENCY_LABEL} from "dolphin/core/config.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {clearMessages, formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {moneyToStorage} from "dolphin/core/money.js";
import {fillSelect, loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {appendCell, appendDetailLink, appendMoneyCell, appendStatusCell} from "dolphin/ui/table.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

function productRow(product) {
    const row = document.createElement("tr");
    appendCell(row, product.sku);
    appendCell(row, product.name);
    appendCell(row, product.category_name || "بدون دسته‌بندی");
    appendCell(row, product.brand || "—");
    appendCell(row, product.unit_display || "—");
    // The price went out raw here while every other table used `money()`,
    // so the products list was the one screen showing `12500000.00`.
    appendMoneyCell(row, product.current_price);
    appendStatusCell(row, (product.is_active));
    appendDetailLink(row, `/products/${product.id}/`);
    return row;
}

export async function setupProducts() {
    const form = document.getElementById("product-search-form");
    setupListFilter("product");
    setupProductImport();
    // Wire the dialog before any awaited load: a click that lands while a
    // network load is still pending would otherwise be silently discarded,
    // leaving the create button inert for the first moments of the page.
    const dialog = document.getElementById("create-product-dialog");
    if (dialog) {
        const createForm = document.getElementById("create-product-form");
        function renderProductReview() {
            renderWizardReview(document.getElementById("create-product-review"), [
                ["کد محصول", document.getElementById("create-product-sku").value],
                ["نام", document.getElementById("create-product-name").value],
                ["دسته‌بندی", selectedOptionText(document.getElementById("create-product-category"))],
                ["برند", document.getElementById("create-product-brand").value || "—"],
                ["واحد", selectedOptionText(document.getElementById("create-product-unit"))],
                [`قیمت جاری (${CURRENCY_LABEL})`, document.getElementById("create-product-price").value || "—"],
                ["شرح", document.getElementById("create-product-description").value || "—"],
            ]);
        }
        const productWizard = setupWizard(dialog, {onReachLastStep: renderProductReview});
        document.getElementById("open-create-product").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            productWizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const payload = formPayload(createForm, ["sku", "name", "brand", "unit", "description"]);
                // The field is grouped text for the operator; the API wants digits.
                payload.current_price = moneyToStorage(new FormData(createForm).get("current_price"));
                payload.category = new FormData(createForm).get("category") ? Number(new FormData(createForm).get("category")) : null;
                const product = await apiRequest(createForm.action, {method: "POST", body: payload});
                window.location.assign(`/products/${product.id}/`);
            });
        });
    }
    try {
        const categories = await loadAllPages("/api/v1/product-categories/?is_active=true&ordering=display_order");
        fillSelect(document.getElementById("product-category-filter"), categories, (category) => category.name, "همه دسته‌بندی‌ها");
        const createCategory = document.getElementById("create-product-category");
        if (createCategory) fillSelect(createCategory, categories, (category) => category.name, "بدون دسته‌بندی");
    } catch (error) {
        showError(error);
    }
    const controller = setupPagedList({
        key: "products",
        form,
        search: document.getElementById("product-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("product-search").value.trim();
            if (search) query.set("search", search);
            const isActive = document.getElementById("product-status-filter").value;
            if (isActive) query.set("is_active", isActive);
            const category = document.getElementById("product-category-filter").value;
            if (category) query.set("category", category);
            // Ordering is no longer a filter control; the list keeps the
            // model's own name ordering.
            return `/api/v1/products/?${query}`;
        },
        renderRow: productRow,
    });
    controller.load();
}

/**
 * Upload a filled export back as new products.
 *
 * The user exports first, writes on that file, and returns it — so the
 * header row is ours and the server maps columns by name rather than by
 * position. Everything about which row is a duplicate, which is invalid and
 * which was created is decided on the server; this only reports what it
 * says.
 */
function setupProductImport() {
    const open = document.getElementById("open-import-products");
    const picker = document.getElementById("import-products-file");
    if (!open || !picker) return;

    open.addEventListener("click", () => picker.click());
    picker.addEventListener("change", async () => {
        const file = picker.files && picker.files[0];
        if (!file) return;
        const body = new FormData();
        body.append("file", file);
        open.disabled = true;
        clearMessages();
        try {
            const result = await apiRequest("/api/v1/products/import-xlsx/", {
                method: "POST", body, raw: true,
            });
            const parts = [`${toPersianDigits(String(result.created))} محصول ثبت شد.`];
            if (result.duplicates) {
                parts.push(`${toPersianDigits(String(result.duplicates))} محصول تکراری بود و اضافه نشد.`);
            }
            if (result.invalid) {
                parts.push(`${toPersianDigits(String(result.invalid))} ردیف نامعتبر بود و رد شد.`);
            }
            // A run with nothing created is not a success message.
            globalMessage(parts.join(" "), result.created > 0);
        } catch (error) {
            showError(error);
        } finally {
            open.disabled = false;
            picker.value = "";
        }
    });
}
