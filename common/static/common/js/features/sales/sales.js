import {SALE_STATUS_TEXT} from "dolphin/features/sales/shared.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {appendCell, appendDetailLink, appendStatusBadgeCell} from "dolphin/ui/table.js";

function saleRow(sale) {
    const row = document.createElement("tr");
    // The campaign the result came from leads the row: these are campaign
    // outcomes, and the campaign is what the reader is scanning for.
    appendCell(row, sale.campaign_name || "—");
    appendCell(row, sale.product_name || sale.product);
    appendCell(row, sale.quantity);
    appendCell(row, sale.total_amount);
    // A badge, not bare text (product-owner request 2026-09-19): this
    // table is scanned for the one cancelled result among a page of
    // confirmed ones, and every other document list in the panel already
    // paints that column. `appendStatusBadgeCell` is that shared helper —
    // nothing new was built for this page.
    appendStatusBadgeCell(row, SALE_STATUS_TEXT, sale.status);
    appendCell(row, sale.sold_by_display || sale.sold_by);
    appendDetailLink(row, `/sales/${sale.id}/`);
    return row;
}

export async function setupSales() {
    const form = document.getElementById("sale-search-form");
    setupListFilter("sale");
    const controller = setupPagedList({
        key: "sales",
        form,
        search: document.getElementById("sale-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page), ordering: document.getElementById("sale-ordering").value});
            const search = document.getElementById("sale-search").value.trim();
            const status = document.getElementById("sale-status").value;
            if (search) query.set("search", search);
            if (status) query.set("status", status);
            return `/api/v1/sales/?${query}`;
        },
        renderRow: saleRow,
    });
    controller.load();
}
