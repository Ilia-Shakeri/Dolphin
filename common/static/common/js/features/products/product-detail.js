import {apiRequest} from "dolphin/core/api.js";
import {clearMessages, formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money, moneyToStorage} from "dolphin/core/money.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {fillSelect, loadAllPages} from "dolphin/ui/lists.js";
import {statusText} from "dolphin/ui/table.js";

function fillProduct(product) {
    document.getElementById("edit-product-sku").value = product.sku;
    document.getElementById("edit-product-name").value = product.name;
    document.getElementById("edit-product-category").value = product.category || "";
    document.getElementById("edit-product-brand").value = product.brand || "";
    document.getElementById("edit-product-unit").value = product.unit || "";
    document.getElementById("edit-product-price").value = moneyDigits(product.current_price);
    document.getElementById("edit-product-description").value = product.description || "";
    document.getElementById("product-created-by").value = product.created_by_display || product.created_by;
    document.getElementById("product-updated-by").value = product.updated_by_display || product.updated_by;
    // A Platform Admin gets a select; everyone else the read-only text.
    const activeSelect = document.getElementById("product-active-select");
    if (activeSelect) {
        activeSelect.value = String(Boolean(product.is_active));
    } else {
        document.getElementById("product-status").value = statusText(product.is_active);
    }
}

export async function setupProductDetail() {
    const productId = document.body.dataset.productId;
    const endpoint = `/api/v1/products/${productId}/`;
    const loading = document.getElementById("product-detail-loading");
    const content = document.getElementById("product-detail-content");
    let product;
    try {
        const [productValue, categories] = await Promise.all([
            apiRequest(endpoint),
            loadAllPages("/api/v1/product-categories/?is_active=true&ordering=display_order"),
        ]);
        product = productValue;
        if (product.category && !categories.some((category) => category.id === product.category)) {
            categories.push({id: product.category, name: `${product.category_name || "دسته‌بندی"} (غیرفعال)`});
        }
        fillSelect(document.getElementById("edit-product-category"), categories, (category) => category.name, "بدون دسته‌بندی");
        fillProduct(product);
        loading.hidden = true;
        content.hidden = false;
    } catch (error) {
        loading.hidden = true;
        showError(error);
        return;
    }
    const form = document.getElementById("edit-product-form");
    if (form.querySelector("button[type='submit']")) {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const payload = formPayload(form, ["sku", "name", "brand", "unit", "description"]);
                payload.current_price = moneyToStorage(new FormData(form).get("current_price"));
                payload.category = new FormData(form).get("category") ? Number(new FormData(form).get("category")) : null;
                product = await apiRequest(endpoint, {method: "PATCH", body: payload});
                fillProduct(product);
                globalMessage("محصول ذخیره شد.", true);
            });
        });
    }
    // Reversible: an inactive product cannot go on a new document, but every
    // existing line keeps its snapshot, so turning it back on restores it.
    const activeSelect = document.getElementById("product-active-select");
    activeSelect?.addEventListener("change", async () => {
        const nextActive = activeSelect.value === "true";
        if (nextActive === Boolean(product.is_active)) return;
        const question = nextActive ? "این محصول دوباره فعال شود؟" : "این محصول غیرفعال شود؟";
        if (!await confirmDialog(question)) {
            activeSelect.value = String(Boolean(product.is_active));
            return;
        }
        activeSelect.disabled = true;
        clearMessages();
        try {
            product = await apiRequest(`${endpoint}set-active/`, {
                method: "POST", body: {is_active: nextActive},
            });
            fillProduct(product);
            globalMessage(nextActive ? "محصول دوباره فعال شد." : "محصول غیرفعال شد.", true);
        } catch (error) {
            activeSelect.value = String(Boolean(product.is_active));
            showError(error);
        } finally {
            activeSelect.disabled = false;
        }
    });
}

/**
 * The same grouping for a text input, without the currency word.
 *
 * Exact, not rounded, and that distinction is the whole reason the
 * option exists: this fills a field the operator is about to save
 * again. In toman a stored `12345` rial is `1234.5` toman, and printing
 * it as `1235` would write `12350` back on the next save — a silent
 * five-rial edit nobody asked for.
 */
function moneyDigits(value) {
    const shown = money(value, {withCurrency: false, exact: true});
    return shown === "—" ? "" : shown;
}
