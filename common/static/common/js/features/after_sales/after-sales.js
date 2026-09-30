import {apiRequest} from "dolphin/core/api.js";
import {displayDate} from "dolphin/core/jalali.js";
import {clearMessages, formPayload, showError, withSubmit} from "dolphin/core/messages.js";
import {fillSelect, loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {appendCell, appendDetailLink} from "dolphin/ui/table.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

function afterSalesRow(item) {
    const row = document.createElement("tr");
    [item.subject, item.customer_name || item.customer, item.status, item.assigned_to_display || "تخصیص‌نیافته", item.closed_at ? "بسته" : "باز", displayDate(item.created_at)].forEach((value) => appendCell(row, value));
    appendDetailLink(row, `/after-sales/${item.id}/`);
    return row;
}

export async function setupAfterSales() {
    const form = document.getElementById("after-sales-search-form");
    setupListFilter("after-sales");
    const controller = setupPagedList({key: "after-sales", form, search: document.getElementById("after-sales-search"), endpoint: (page) => {
        const query = new URLSearchParams({page: String(page), ordering: document.getElementById("after-sales-ordering").value});
        const search = document.getElementById("after-sales-search").value.trim(); if (search) query.set("search", search);
        [["status", "after-sales-status"], ["assigned_to", "after-sales-assignee"], ["is_closed", "after-sales-closed"]].forEach(([name, id]) => { const node = document.getElementById(id); const value = node?.value.trim(); if (value) query.set(name, value); });
        return `/api/v1/after-sales/?${query}`;
    }, renderRow: afterSalesRow});
    controller.load();
    const dialog = document.getElementById("create-after-sales-dialog");
    if (!dialog) return;
    const customerSelect = document.getElementById("create-after-sales-customer");
    const saleSelect = document.getElementById("create-after-sales-sale");
    const documentSelect = document.getElementById("create-after-sales-document");
    const assigneeSelect = document.getElementById("create-after-sales-assigned");
    let sales = [], documents = [];
    function renderAfterSalesReview() {
        renderWizardReview(document.getElementById("create-after-sales-review"), [
            ["مشتری", selectedOptionText(customerSelect)],
            ["فروش اختیاری", selectedOptionText(saleSelect)],
            ["سند عملیاتی اختیاری", selectedOptionText(documentSelect)],
            ["مسئول اختیاری", selectedOptionText(assigneeSelect)],
            // `|| "—"` on all three, the convention every other review
            // uses: an optional field left empty should read as an em dash
            // rather than as a label with nothing beside it.
            ["موضوع", document.getElementById("create-after-sales-subject").value || "—"],
            ["وضعیت آغازین", document.getElementById("create-after-sales-status").value || "—"],
            ["شرح", document.getElementById("create-after-sales-description").value || "—"],
        ]);
    }
    const afterSalesWizard = setupWizard(dialog, {onReachLastStep: renderAfterSalesReview});
    // Wire the dialog before the awaited loads below, so a click during
    // them opens the dialog instead of being silently discarded.
    customerSelect.addEventListener("change", refreshRelations);
    document.getElementById("open-create-after-sales").addEventListener("click", () => {
        document.getElementById("create-after-sales-form").reset();
        clearMessages(document.getElementById("create-after-sales-form"));
        afterSalesWizard?.goFirst();
        dialog.showModal();
    });
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    try {
        const [customers, loadedSales, loadedDocuments, assignees] = await Promise.all([
            loadAllPages("/api/v1/customers/?ordering=full_name"), loadAllPages("/api/v1/sales/?ordering=-sold_at"),
            loadAllPages("/api/v1/sales-documents/?ordering=-registered_at"), loadAllPages("/api/v1/after-sales/assignees/"),
        ]);
        sales = loadedSales; documents = loadedDocuments;
        fillSelect(customerSelect, customers, (item) => item.full_name, "یک مشتری انتخاب کنید");
        fillSelect(assigneeSelect, assignees, (item) => item.display, "فعلا تخصیص ندهید");
    } catch (error) { showError(error); }
    function refreshRelations() {
        const id = Number(customerSelect.value);
        fillSelect(saleSelect, sales.filter((item) => Number(item.customer) === id), (item) => `فروش ${item.id}`, "بدون فروش");
        fillSelect(documentSelect, documents.filter((item) => Number(item.customer) === id), (item) => item.document_number, "بدون سند");
    }
    const createForm = document.getElementById("create-after-sales-form");
    createForm.addEventListener("submit", (event) => { event.preventDefault(); withSubmit(createForm, async () => {
        const payload = formPayload(createForm, ["customer", "sale", "document", "assigned_to", "subject", "description", "status"]);
        ["sale", "document", "assigned_to"].forEach((name) => { if (!payload[name]) delete payload[name]; });
        const item = await apiRequest(createForm.action, {method: "POST", body: payload}); window.location.assign(`/after-sales/${item.id}/`);
    }); });
}
