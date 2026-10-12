import {apiRequest} from "dolphin/core/api.js";
import {formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {liveRecord} from "dolphin/ui/live-record.js";
import {statusText} from "dolphin/ui/table.js";

function fillProductCategory(category) {
    document.getElementById("edit-product-category-code").value = category.code;
    document.getElementById("edit-product-category-name").value = category.name;
    document.getElementById("edit-product-category-order").value = category.display_order;
    document.getElementById("edit-product-category-description").value = category.description || "";
    document.getElementById("product-category-status").value = statusText(category.is_active);
    document.getElementById("product-category-created-by").value = category.created_by_display || category.created_by;
    document.getElementById("product-category-updated-by").value = category.updated_by_display || category.updated_by;
    const toggle = document.getElementById("toggle-product-category");
    if (toggle) {
        toggle.textContent = category.is_active ? "غیرفعال کردن دسته‌بندی" : "فعال کردن دوباره دسته‌بندی";
        toggle.classList.toggle("btn-danger", category.is_active);
    }
}

export async function setupProductCategoryDetail() {
    const categoryId = document.body.dataset.categoryId;
    const endpoint = `/api/v1/product-categories/${categoryId}/`;
    const loading = document.getElementById("product-category-detail-loading");
    const content = document.getElementById("product-category-detail-content");
    let category;
    // Live (2.40.41): the record redraws in place when it changes elsewhere.
    const show = (value) => { category = value; fillProductCategory(value); settle(value); };
    const settle = liveRecord({read: () => apiRequest(endpoint), draw: show});
    try {
        show(await apiRequest(endpoint));
        loading.hidden = true;
        content.hidden = false;
    } catch (error) {
        loading.hidden = true;
        showError(error);
        return;
    }
    const form = document.getElementById("edit-product-category-form");
    if (form.querySelector("button[type='submit']")) {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const payload = formPayload(form, ["name", "description"]);
                payload.display_order = Number(new FormData(form).get("display_order"));
                show(await apiRequest(endpoint, {method: "PATCH", body: payload}));
                globalMessage("دسته‌بندی ذخیره شد.", true);
            });
        });
    }
    const toggle = document.getElementById("toggle-product-category");
    toggle?.addEventListener("click", async () => {
        const action = category.is_active ? "deactivate" : "reactivate";
        const prompt = category.is_active ? "این دسته‌بندی غیرفعال شود؟" : "این دسته‌بندی دوباره فعال شود؟";
        if (!await confirmDialog(prompt)) return;
        toggle.disabled = true;
        try {
            show(await apiRequest(`${endpoint}${action}/`, {method: "POST"}));
            globalMessage(category.is_active ? "دسته‌بندی فعال شد." : "دسته‌بندی غیرفعال شد.", true);
        } catch (error) {
            showError(error);
        } finally {
            toggle.disabled = false;
        }
    });
}
