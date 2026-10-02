import {apiRequest} from "dolphin/core/api.js";
import {apiDateTime, displayDay, localDateTimeValue} from "dolphin/core/jalali.js";
import {DOCUMENT_STATUS_TEXT} from "dolphin/core/labels.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {textOrNull} from "dolphin/core/money.js";
import {documentLineEditor} from "dolphin/features/billing/shared.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {appendCell, appendMoneyCell, labelled} from "dolphin/ui/table.js";

export async function setupOrderDetail() {
    const orderId = document.body.dataset.orderId;
    const endpoint = `/api/v1/orders/${orderId}/`;
    const loading = document.getElementById("order-detail-loading");
    const content = document.getElementById("order-detail-content");
    const statusSelect = document.getElementById("order-status-select");
    const form = document.getElementById("edit-order-form");
    const editActions = document.getElementById("order-edit-actions");
    const lockedNote = document.getElementById("order-locked-note");
    const lines = documentLineEditor({doc: "order", endpoint, onSaved: (updated) => apply(updated)});

    let current = null;

    function apply(order) {
        current = order;
        document.getElementById("order-number").value = order.number;
        document.getElementById("order-customer").value = order.customer_name;
        // A request made from an invoice names it; its customer and lines come from there.
        const invoiceRow = document.getElementById("order-invoice-row");
        if (invoiceRow) {
            invoiceRow.hidden = !order.invoice;
            if (order.invoice) {
                const link = document.getElementById("order-invoice-link");
                link.href = `/invoices/${order.invoice}/`;
                link.textContent = order.invoice_number || String(order.invoice);
            }
        }
        // Registration is server-generated and immutable, shown as a day.
        document.getElementById("order-registered-at").value = displayDay(order.created_at);
        document.getElementById("order-created-by").value = order.created_by_display || order.created_by;
        if (statusSelect) {
            statusSelect.value = order.status;
        } else {
            document.getElementById("order-status").value = labelled(DOCUMENT_STATUS_TEXT, order.status);
        }
        document.getElementById("edit-order-delivery").value = localDateTimeValue(order.expected_delivery_at);
        document.getElementById("edit-order-notes").value = order.notes || "";
        // A draft and an approved order are both editable: the service moves
        // only the stock difference when an approved one changes.
        const editable = ["draft", "confirmed"].includes(order.status);
        if (editActions) editActions.hidden = !editable;
        if (lockedNote) lockedNote.hidden = editable;
        form.querySelectorAll("input[name], textarea[name]").forEach((field) => { field.disabled = !editable; });
        lines.apply(order);
    }

    /**
     * Invoices linked to this order.
     *
     * Read through the real relation — `?order=<id>` — rather than by
     * comparing document numbers as text.
     */
    async function loadLinkedInvoices() {
        const wrap = document.getElementById("order-invoices-table-wrap");
        const body = document.getElementById("order-invoices-table-body");
        const invoiceLoading = document.getElementById("order-invoices-loading");
        const empty = document.getElementById("order-invoices-empty");
        if (!wrap || !body) return;
        invoiceLoading.hidden = false; wrap.hidden = true; empty.hidden = true;
        try {
            const data = await apiRequest(`/api/v1/invoices/?order=${orderId}`);
            body.replaceChildren(...data.results.map((invoice) => {
                const row = document.createElement("tr");
                appendCell(row, invoice.number).dir = "ltr";
                appendMoneyCell(row, invoice.total_amount);
                const cell = document.createElement("td");
                const link = document.createElement("a");
                link.className = "btn btn-sm btn-light";
                link.href = `/invoices/${invoice.id}/`;
                link.textContent = "مشاهده";
                cell.append(link);
                row.append(cell);
                return row;
            }));
            invoiceLoading.hidden = true;
            empty.hidden = data.results.length > 0;
            wrap.hidden = data.results.length === 0;
        } catch (error) {
            invoiceLoading.hidden = true;
            showError(error);
        }
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const data = new FormData(form);
            // Document discount and tax rate are not offered on this form.
            const payload = {notes: String(data.get("notes") || "")};
            payload.expected_delivery_at = apiDateTime(textOrNull(data.get("expected_delivery_at")));
            const updated = await apiRequest(endpoint, {method: "PATCH", body: payload});
            apply(updated);
            globalMessage("سربرگ درخواست تأمین ذخیره شد.", true);
        });
    });
    // Changing the status is what moves stock, so it asks first and reports
    // what the server decided — an approval the warehouse cannot cover comes
    // back cancelled, with the reason on the order.
    statusSelect?.addEventListener("change", async () => {
        const next = statusSelect.value;
        if (!current || next === current.status) return;
        const label = labelled(DOCUMENT_STATUS_TEXT, next);
        if (!await confirmDialog(`وضعیت درخواست تأمین به «${label}» تغییر کند؟`)) {
            statusSelect.value = current.status;
            return;
        }
        statusSelect.disabled = true;
        clearMessages();
        try {
            const updated = await apiRequest(`${endpoint}transition/`, {
                method: "POST", body: {to_status: next},
            });
            apply(updated);
            if (updated.status === "cancelled" && next !== "cancelled") {
                globalMessage("موجودی کافی نبود؛ درخواست تأمین لغو شد.");
            } else {
                globalMessage("وضعیت درخواست تأمین ثبت شد.", true);
            }
        } catch (error) {
            statusSelect.value = current.status;
            showError(error);
        } finally {
            statusSelect.disabled = false;
        }
    });

    try {
        const [order] = await Promise.all([apiRequest(endpoint), lines.loadProducts()]);
        apply(order);
        await loadLinkedInvoices();
        loading.hidden = true;
        content.hidden = false;
    } catch (error) {
        loading.hidden = true;
        showError(error);
    }
}
