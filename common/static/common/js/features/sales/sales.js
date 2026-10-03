import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {clearMessages, formPayload, showError, withSubmit} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {SALE_STATUS_TEXT} from "dolphin/features/sales/shared.js";
import {fillSelect, loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {appendCell, appendDetailLink, appendStatusBadgeCell} from "dolphin/ui/table.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

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
    const dialog = document.getElementById("create-sale-dialog");
    const createForm = document.getElementById("create-sale-form");
    function renderSaleReview() {
        renderWizardReview(document.getElementById("create-sale-review"), [
            ["سرنخ مجاز", selectedOptionText(document.getElementById("create-sale-lead"))],
            ["محصول فعال", selectedOptionText(document.getElementById("create-sale-product"))],
            ["تعداد", toPersianDigits(document.getElementById("create-sale-quantity").value)],
            ["یادداشت", document.getElementById("create-sale-notes").value || "—"],
        ]);
    }
    const saleWizard = setupWizard(dialog, {onReachLastStep: renderSaleReview});
    // The entry point is a link to the invoice flow now (2.39.3); the dialog
    // opens only from a legacy `?lead=` deep link, if a button is ever present.
    const openButton = document.getElementById("open-create-sale");
    if (openButton?.tagName === "BUTTON") openButton.addEventListener("click", () => {
        createForm.reset();
        clearMessages(createForm);
        saleWizard?.goFirst();
        dialog.showModal();
    });
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    try {
        const me = await apiRequest("/api/v1/auth/me/");
        let leads = await loadAllPages("/api/v1/leads/?ordering=-created_at");
        const products = await loadAllPages("/api/v1/products/?ordering=name");
        if (me.role === "sales_agent") leads = leads.filter((lead) => Number(lead.assigned_to) === Number(me.id));
        const leadSelect = document.getElementById("create-sale-lead");
        fillSelect(leadSelect, leads, (lead) => `${lead.customer_name} — ${lead.source}`, "یک سرنخ انتخاب کنید");
        fillSelect(document.getElementById("create-sale-product"), products.filter((product) => product.is_active), (product) => `${product.name} — ${money(product.current_price)}`, "یک محصول انتخاب کنید");
        const requestedLead = new URLSearchParams(window.location.search).get("lead");
        if (requestedLead && leads.some((lead) => String(lead.id) === requestedLead)) {
            leadSelect.value = requestedLead;
            saleWizard?.goFirst();
            dialog.showModal();
        }
    } catch (error) {
        showError(error);
    }
    createForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(createForm, async () => {
            const payload = formPayload(createForm, ["lead", "product", "quantity", "notes"]);
            const sale = await apiRequest(createForm.action, {method: "POST", body: payload});
            window.location.assign(`/sales/${sale.id}/`);
        });
    });
}
