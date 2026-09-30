import {apiRequest} from "dolphin/core/api.js";
import {displayDate} from "dolphin/core/jalali.js";
import {formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {SALE_STATUS_TEXT} from "dolphin/features/sales/shared.js";
import {labelled} from "dolphin/ui/table.js";

function saleStatusText(value) {
    return labelled(SALE_STATUS_TEXT, value);
}

function fillSale(sale) {
    document.getElementById("sale-lead").value = sale.lead;
    document.getElementById("sale-customer").value = sale.customer_name || sale.customer;
    document.getElementById("sale-product").value = sale.product_name || sale.product || "—";
    document.getElementById("sale-seller").value = sale.sold_by_display || sale.sold_by;
    document.getElementById("sale-quantity").value = sale.quantity;
    // These are read-only boxes, so they get the same rial formatting as
    // every table cell rather than the raw two-decimal string.
    document.getElementById("sale-unit-price").value = money(sale.unit_price_snapshot);
    document.getElementById("sale-total").value = money(sale.total_amount);
    document.getElementById("sale-detail-status").value = saleStatusText(sale.status);
    document.getElementById("sale-time").value = displayDate(sale.sold_at);
    document.getElementById("sale-notes").value = sale.notes || "";
    const cancelSection = document.getElementById("sale-cancel-section");
    if (cancelSection) cancelSection.hidden = sale.status !== "confirmed";
}

export async function setupSaleDetail() {
    const saleId = document.body.dataset.saleId;
    const endpoint = `/api/v1/sales/${saleId}/`;
    const loading = document.getElementById("sale-detail-loading");
    const content = document.getElementById("sale-detail-content");
    let sale;
    try {
        sale = await apiRequest(endpoint);
        fillSale(sale);
        loading.hidden = true;
        content.hidden = false;
    } catch (error) {
        loading.hidden = true;
        showError(error);
        return;
    }
    const form = document.getElementById("cancel-sale-form");
    form?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            sale = await apiRequest(form.action, {method: "POST", body: formPayload(form, ["reason"])});
            fillSale(sale);
            globalMessage("فروش لغو شد.", true);
        });
    });
}
