import {displayDate} from "dolphin/core/jalali.js";
import {showError} from "dolphin/core/messages.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {loadWarehouseOptions} from "dolphin/ui/searchable-select.js";
import {appendCell, appendMoneyCell, appendStatusBadgeCell} from "dolphin/ui/table.js";

const MOVEMENT_TEXT = Object.freeze({
    opening: "موجودی اول دوره",
    purchase: "رسید خرید",
    sale: "خروج فروش",
    return_in: "برگشت از مشتری",
    return_out: "برگشت به تأمین‌کننده",
    adjustment_in: "اصلاح افزایشی",
    adjustment_out: "اصلاح کاهشی",
    transfer_in: "انتقال ورودی",
    transfer_out: "انتقال خروجی",
});

function stockMovementRow(movement) {
    const row = document.createElement("tr");
    appendCell(row, displayDate(movement.occurred_at));
    appendCell(row, movement.warehouse_name);
    appendCell(row, movement.product_name);
    appendStatusBadgeCell(row, MOVEMENT_TEXT, movement.movement_type);
    appendCell(row, movement.quantity);
    appendMoneyCell(row, movement.unit_cost);
    appendCell(row, movement.resulting_quantity);
    appendCell(row, movement.reference_number || "—").dir = "ltr";
    appendCell(row, movement.created_by_display || movement.created_by);
    return row;
}

export async function setupStockMovements() {
    const form = document.getElementById("stock-movement-search-form");
    setupListFilter("stock-movement");
    try {
        await loadWarehouseOptions(document.getElementById("stock-movement-warehouse"), "همه انبارها");
    } catch (error) {
        showError(error);
    }
    const controller = setupPagedList({
        key: "stock-movements",
        form,
        search: document.getElementById("stock-movement-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("stock-movement-search").value.trim();
            if (search) query.set("search", search);
            const warehouse = document.getElementById("stock-movement-warehouse").value;
            if (warehouse) query.set("warehouse", warehouse);
            const movementType = document.getElementById("stock-movement-type").value;
            if (movementType) query.set("movement_type", movementType);
            query.set("ordering", document.getElementById("stock-movement-ordering").value);
            return `/api/v1/stock-movements/?${query}`;
        },
        renderRow: stockMovementRow,
    });
    controller.load();
}
