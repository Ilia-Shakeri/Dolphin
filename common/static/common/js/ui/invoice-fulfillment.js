import {apiRequest} from "dolphin/core/api.js";
import {globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {DOCUMENT_STATUS_TEXT} from "dolphin/core/labels.js";
import {loadAllPages} from "dolphin/ui/lists.js";
import {labelled} from "dolphin/ui/table.js";

/**
 * The «درخواست تأمین از انبار» card on an issued invoice (2.37.0).
 *
 * Shows the invoice's requests and, when none is open, lets the marketer or the
 * manager ask the warehouse to supply it. The form carries a warehouse and an
 * optional note only: the customer, the lines and the prices come from the
 * invoice on the server, which also refuses the request when the invoice is not
 * issued, already has an open request, or already took its stock.
 */
export async function setupInvoiceFulfillment(invoiceId, status) {
    const card = document.getElementById("invoice-fulfillment");
    if (!card || status !== "issued") return;
    const list = card.querySelector("[data-fulfillment-list]");
    const form = card.querySelector("[data-fulfillment-form]");
    const select = form.elements.warehouse;

    async function refresh() {
        const data = await apiRequest(`/api/v1/orders/?invoice=${invoiceId}`);
        list.replaceChildren(...data.results.map((request) => {
            const item = document.createElement("li");
            const link = document.createElement("a");
            link.href = `/orders/${request.id}/`;
            link.textContent = request.number;
            item.append(link, ` — ${labelled(DOCUMENT_STATUS_TEXT, request.status)}`);
            return item;
        }));
        const open = data.results.some((request) => request.status !== "cancelled");
        form.hidden = open;
        return data.results.length;
    }

    try {
        await refresh();
        card.hidden = false;
        const warehouses = await loadAllPages("/api/v1/warehouses/?is_active=true&ordering=name");
        select.replaceChildren(new Option("انتخاب انبار", ""), ...warehouses.map((row) => new Option(row.name, String(row.id))));
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                await apiRequest("/api/v1/orders/from-invoice/", {
                    method: "POST",
                    body: {invoice: Number(invoiceId), warehouse: Number(select.value), notes: form.elements.notes.value},
                });
                globalMessage("درخواست تأمین از انبار ثبت شد.", true);
                await refresh();
            });
        });
    } catch (error) {
        // A deployment or role without orders simply has no card.
        if (error?.status && error.status !== 403 && error.status !== 404) showError(error);
    }
}
