import {apiRequest} from "dolphin/core/api.js";
import {clearMessages, formPayload, withSubmit} from "dolphin/core/messages.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {appendCell, appendDetailLink, appendStatusCell} from "dolphin/ui/table.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

// --- Warehouses ---------------------------------------------------------

function warehouseRow(warehouse) {
    const row = document.createElement("tr");
    appendCell(row, warehouse.code);
    appendCell(row, warehouse.name);
    appendCell(row, warehouse.address);
    appendCell(row, warehouse.is_default ? "بله" : "خیر");
    appendStatusCell(row, (warehouse.is_active));
    appendDetailLink(row, `/warehouses/${warehouse.id}/`);
    return row;
}

export function setupWarehouses() {
    const form = document.getElementById("warehouse-search-form");
    setupListFilter("warehouse");
    const dialog = document.getElementById("create-warehouse-dialog");
    if (dialog) {
        const createForm = document.getElementById("create-warehouse-form");
        function renderReview() {
            renderWizardReview(document.getElementById("create-warehouse-review"), [
                ["کد انبار", document.getElementById("create-warehouse-code").value],
                ["نام", document.getElementById("create-warehouse-name").value],
                ["انبار پیش‌فرض", selectedOptionText(document.getElementById("create-warehouse-default"))],
                ["نشانی", document.getElementById("create-warehouse-address").value || "—"],
            ]);
        }
        const wizard = setupWizard(dialog, {onReachLastStep: renderReview});
        document.getElementById("open-create-warehouse").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            wizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const payload = formPayload(createForm, ["code", "name", "address"]);
                payload.is_default = new FormData(createForm).get("is_default") === "true";
                const warehouse = await apiRequest(createForm.action, {method: "POST", body: payload});
                window.location.assign(`/warehouses/${warehouse.id}/`);
            });
        });
    }
    const controller = setupPagedList({
        key: "warehouses",
        form,
        search: document.getElementById("warehouse-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("warehouse-search").value.trim();
            if (search) query.set("search", search);
            const isActive = document.getElementById("warehouse-status-filter").value;
            if (isActive) query.set("is_active", isActive);
            query.set("ordering", document.getElementById("warehouse-ordering").value);
            return `/api/v1/warehouses/?${query}`;
        },
        renderRow: warehouseRow,
    });
    controller.load();
}
