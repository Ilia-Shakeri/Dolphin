import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {clearMessages, formPayload, withSubmit} from "dolphin/core/messages.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {appendCell, appendDetailLink, appendStatusCell} from "dolphin/ui/table.js";
import {renderWizardReview, setupWizard} from "dolphin/ui/wizard.js";

function productCategoryRow(category) {
    const row = document.createElement("tr");
    appendCell(row, category.display_order);
    appendCell(row, category.code).dir = "ltr";
    appendCell(row, category.name);
    appendStatusCell(row, (category.is_active));
    appendDetailLink(row, `/product-categories/${category.id}/`);
    return row;
}

export function setupProductCategories() {
    const form = document.getElementById("product-category-search-form");
    setupListFilter("product-category");
    const controller = setupPagedList({
        key: "product-categories",
        form,
        search: document.getElementById("product-category-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("product-category-search").value.trim();
            if (search) query.set("search", search);
            const isActive = document.getElementById("product-category-status-filter").value;
            if (isActive) query.set("is_active", isActive);
            query.set("ordering", document.getElementById("product-category-ordering").value);
            return `/api/v1/product-categories/?${query}`;
        },
        renderRow: productCategoryRow,
    });
    const dialog = document.getElementById("create-product-category-dialog");
    if (dialog) {
        const createForm = document.getElementById("create-product-category-form");
        function renderReview() {
            renderWizardReview(document.getElementById("create-product-category-review"), [
                ["کد پایدار", document.getElementById("create-product-category-code").value],
                ["نام", document.getElementById("create-product-category-name").value],
                ["ترتیب نمایش", toPersianDigits(document.getElementById("create-product-category-order").value)],
                ["شرح", document.getElementById("create-product-category-description").value || "—"],
            ]);
        }
        const wizard = setupWizard(dialog, {onReachLastStep: renderReview});
        document.getElementById("open-create-product-category").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            wizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const payload = formPayload(createForm, ["code", "name", "description"]);
                payload.display_order = Number(new FormData(createForm).get("display_order"));
                const category = await apiRequest(createForm.action, {method: "POST", body: payload});
                window.location.assign(`/product-categories/${category.id}/`);
            });
        });
    }
    controller.load();
}
