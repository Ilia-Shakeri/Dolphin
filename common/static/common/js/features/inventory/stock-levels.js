import {apiRequest} from "dolphin/core/api.js";
import {displayDate} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {moneyOrNull} from "dolphin/core/money.js";
import {fillSelect, loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {loadWarehouseOptions} from "dolphin/ui/searchable-select.js";
import {appendCell, appendMoneyCell} from "dolphin/ui/table.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

async function loadProductOptions(select, emptyLabel) {
    if (!select) return [];
    const rows = await loadAllPages("/api/v1/products/?is_active=true&ordering=name");
    fillSelect(select, rows, (row) => `${row.name} (${row.sku})`, emptyLabel);
    return rows;
}

// --- Stock levels and movements -----------------------------------------

function stockItemRow(item) {
    const row = document.createElement("tr");
    appendCell(row, item.warehouse_name);
    appendCell(row, item.product_sku).dir = "ltr";
    appendCell(row, item.product_name);
    appendCell(row, item.quantity);
    appendMoneyCell(row, item.average_cost);
    appendMoneyCell(row, item.stock_value);
    appendCell(row, displayDate(item.last_movement_at));
    return row;
}

export async function setupStockLevels() {
    const form = document.getElementById("stock-search-form");
    setupListFilter("stock");
    const movementDialog = document.getElementById("create-movement-dialog");
    const transferDialog = document.getElementById("transfer-stock-dialog");
    let controller = null;

    // Handlers are attached before any awaited load so a click landing in
    // the first moments of the page is not silently discarded.
    if (movementDialog) {
        const createForm = document.getElementById("create-movement-form");
        function renderMovementReview() {
            renderWizardReview(document.getElementById("create-movement-review"), [
                ["انبار", selectedOptionText(document.getElementById("create-movement-warehouse"))],
                ["کالا", selectedOptionText(document.getElementById("create-movement-product"))],
                ["نوع حرکت", selectedOptionText(document.getElementById("create-movement-type"))],
                ["تعداد", createForm.quantity.value || "—"],
                ["بهای واحد", createForm.unit_cost.value || "—"],
                ["یادداشت", createForm.notes.value || "—"],
            ]);
        }
        const movementWizard = setupWizard(movementDialog, {onReachLastStep: renderMovementReview});
        document.getElementById("open-create-movement").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            movementWizard?.goFirst();
            movementDialog.showModal();
        });
        movementDialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => movementDialog.close()));
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const data = new FormData(createForm);
                const payload = {
                    warehouse: Number(data.get("warehouse")),
                    product: Number(data.get("product")),
                    movement_type: String(data.get("movement_type")),
                    quantity: Number(data.get("quantity")),
                    notes: String(data.get("notes") || ""),
                };
                const cost = moneyOrNull(data.get("unit_cost"));
                if (cost !== null) payload.unit_cost = cost;
                await apiRequest(createForm.action, {method: "POST", body: payload});
                movementDialog.close();
                globalMessage("حرکت انبار ثبت شد.", true);
                controller?.load();
            });
        });
    }
    if (transferDialog) {
        const transferForm = document.getElementById("transfer-stock-form");
        function renderTransferReview() {
            renderWizardReview(document.getElementById("transfer-stock-review"), [
                ["از انبار", selectedOptionText(document.getElementById("transfer-from-warehouse"))],
                ["به انبار", selectedOptionText(document.getElementById("transfer-to-warehouse"))],
                ["کالا", selectedOptionText(document.getElementById("transfer-product"))],
                ["تعداد", transferForm.quantity.value || "—"],
                ["یادداشت", transferForm.notes.value || "—"],
            ]);
        }
        const transferWizard = setupWizard(transferDialog, {onReachLastStep: renderTransferReview});
        document.getElementById("open-transfer-stock").addEventListener("click", () => {
            transferForm.reset();
            clearMessages(transferForm);
            transferWizard?.goFirst();
            transferDialog.showModal();
        });
        transferDialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => transferDialog.close()));
        transferForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(transferForm, async () => {
                const data = new FormData(transferForm);
                await apiRequest(transferForm.action, {method: "POST", body: {
                    from_warehouse: Number(data.get("from_warehouse")),
                    to_warehouse: Number(data.get("to_warehouse")),
                    product: Number(data.get("product")),
                    quantity: Number(data.get("quantity")),
                    notes: String(data.get("notes") || ""),
                }});
                transferDialog.close();
                globalMessage("انتقال بین انبار ثبت شد.", true);
                controller?.load();
            });
        });
    }

    try {
        const [warehouses] = await Promise.all([
            loadWarehouseOptions(document.getElementById("stock-warehouse-filter"), "همه انبارها"),
            loadProductOptions(document.getElementById("create-movement-product"), "یک کالا انتخاب کنید"),
            loadProductOptions(document.getElementById("transfer-product"), "یک کالا انتخاب کنید"),
        ]);
        [
            ["create-movement-warehouse", "یک انبار انتخاب کنید"],
            ["transfer-from-warehouse", "انبار مبدأ"],
            ["transfer-to-warehouse", "انبار مقصد"],
        ].forEach(([id, emptyLabel]) => {
            const select = document.getElementById(id);
            if (select) fillSelect(select, warehouses, (row) => row.name, emptyLabel);
        });
    } catch (error) {
        showError(error);
    }

    controller = setupPagedList({
        key: "stock-items",
        form,
        search: document.getElementById("stock-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("stock-search").value.trim();
            if (search) query.set("search", search);
            const warehouse = document.getElementById("stock-warehouse-filter").value;
            if (warehouse) query.set("warehouse", warehouse);
            const threshold = document.getElementById("stock-threshold").value.trim();
            if (threshold) query.set("below_or_equal", threshold);
            query.set("ordering", document.getElementById("stock-ordering").value);
            return `/api/v1/stock-items/?${query}`;
        },
        renderRow: stockItemRow,
    });
    controller.load();
}
