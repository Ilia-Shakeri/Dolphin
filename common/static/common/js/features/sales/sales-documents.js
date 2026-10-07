import {apiRequest} from "dolphin/core/api.js";
import {clearMessages, formPayload, showError, withSubmit} from "dolphin/core/messages.js";
import {setupPostalPane} from "dolphin/features/sales/postal-pane.js";
import {fillPostalStates, postalBadge} from "dolphin/features/sales/shared.js";
import {onRealtime} from "dolphin/ui/realtime.js";
import {fillSelect, loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

/**
 * The four postal stops as small connected icons — the row version of
 * `renderPostalStepper`'s own card.
 *
 * Product owner, 2026-09-21: «وضعیت پستی باید ۴ تا ایکون پست سرهم به هم
 * متصل باشد و در هر مرحله‌ای است باید این ایکون روشن باشد». The list
 * this belongs to is «رهگیری پستی» (`sales_documents/list.html`) — a
 * table of documents, not one document's own page — so each row gets
 * the compact form: icons only, no label or description text, the
 * current stage's icon lit and named in a `title` for anyone who
 * hovers or uses a screen reader. `item.postal_stepper` is the same
 * four-entry list `SalesDocumentSerializer` already computes from
 * `sales/postal.py` for the detail page; nothing about the states,
 * their order or their icons is repeated here.
 *
 * A document whose stored status predates the vocabulary (free text)
 * gets an empty `postal_stepper` from the server, and this falls back
 * to that raw text — the same choice `renderPostalStepper` makes for
 * the same reason: four icons with none of them current would claim to
 * know where the parcel is when nobody does.
 */
function postalStatusCell(row, item, cell = document.createElement("td")) {
    const steps = item.postal_stepper;
    // The post office's own status, with its icon, beside the stepper
    // (2.40.26) — and alone for a status outside the four stages (a return,
    // a seizure), which the stepper cannot place.
    const badge = postalBadge(item.postal_badge);
    if (!steps || !steps.length) {
        if (badge) cell.append(badge);
        else cell.textContent = item.postal_status || "—";
        row.appendChild(cell);
        return;
    }
    const list = document.createElement("ul");
    list.className = "postal-mini-stepper";
    const current = steps.find((step) => step.stage === "current");
    list.setAttribute("aria-label", `وضعیت پستی: ${current ? current.label : item.postal_status_display || ""}`);
    list.append(...steps.map((step) => {
        const mark = document.createElement("li");
        mark.className = `postal-mini-step postal-mini-step-${step.stage}`;
        mark.title = step.label;
        const icon = document.createElement("i");
        icon.className = `di-duotone ${step.icon} fs-6`;
        for (let path = 1; path <= (step.icon_paths || 2); path += 1) {
            icon.appendChild(document.createElement("span")).className = `path${path}`;
        }
        mark.append(icon);
        return mark;
    }));
    const wrap = document.createElement("div");
    wrap.className = "d-flex flex-column align-items-start gap-1";
    wrap.append(list);
    if (badge) wrap.append(badge);
    cell.append(wrap);
    row.appendChild(cell);
}

/**
 * One shipment as a card in the list pane (2.40.34): number and post status
 * on top, the customer, then where it is going and its four stages. The whole
 * card opens the shipment in the pane beside it; a real link inside keeps
 * «open in a new tab» working.
 */
function salesDocumentRow(item) {
    const row = document.createElement("tr");
    row.className = "postal-list-row";
    row.dataset.documentId = String(item.id);
    if (!item.is_active) row.classList.add("is-inactive");
    const cell = document.createElement("td");
    const card = document.createElement("div");
    card.className = "postal-list-item";
    const top = document.createElement("div");
    top.className = "postal-list-top";
    const link = document.createElement("a");
    link.className = "postal-list-number";
    link.href = `/sales-documents/${item.id}/`;
    link.dir = "ltr";
    link.textContent = item.document_number;
    top.append(link);
    const customer = document.createElement("div");
    customer.className = "postal-list-customer";
    customer.textContent = item.customer_name || "—";
    const place = document.createElement("div");
    place.className = "postal-list-place";
    place.textContent = [item.province_snapshot, item.city_snapshot].filter(Boolean).join(" / ") || "بدون نشانی";
    const status = document.createElement("div");
    status.className = "postal-list-status";
    postalStatusCell(row, item, status);
    card.append(top, customer, place, status);
    cell.append(card);
    row.append(cell);
    return row;
}

export async function setupSalesDocuments() {
    const form = document.getElementById("sales-document-search-form");
    setupListFilter("sales-document");
    const controller = setupPagedList({
        key: "sales-documents",
        form,
        search: document.getElementById("sales-document-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page), ordering: document.getElementById("sales-document-ordering").value});
            const search = document.getElementById("sales-document-search").value.trim();
            if (search) query.set("search", search);
            [["postal_status", "sales-document-postal-status"], ["province", "sales-document-province"], ["city", "sales-document-city"], ["is_active", "sales-document-active"]].forEach(([name, id]) => {
                const value = document.getElementById(id).value.trim();
                if (value) query.set(name, value);
            });
            return `/api/v1/sales-documents/?${query}`;
        },
        renderRow: salesDocumentRow,
    });
    // Every stage and every Iran Post status (2.40.26), grouped.
    try {
        await fillPostalStates(document.getElementById("sales-document-postal-status"), {emptyLabel: "همهٔ وضعیت‌ها"});
    } catch (error) { showError(error); }

    // Two panes (2.40.34): a card opens its shipment beside the list; the
    // address keeps it (`?doc=`), so a link or a reload opens the same one.
    const workspace = document.getElementById("postal-workspace");
    const body = document.getElementById("sales-documents-table-body");
    const pane = workspace ? setupPostalPane({workspace, onChanged: () => controller.load(controller.page, {quiet: true})}) : null;
    const mark = () => body.querySelectorAll("[data-document-id]").forEach((row) => {
        row.classList.toggle("is-selected", row.dataset.documentId === pane?.shownId);
    });
    const open = (id) => {
        pane.show(id);
        const url = new URL(window.location.href);
        url.searchParams.set("doc", id);
        window.history.replaceState(null, "", url);
        mark();
    };
    body.addEventListener("click", (event) => {
        if (!pane || event.target.closest("input, a")) return;
        const row = event.target.closest("[data-document-id]");
        if (row) open(row.dataset.documentId);
    });
    new MutationObserver(mark).observe(body, {childList: true});
    await controller.load();
    const wanted = new URLSearchParams(window.location.search).get("doc");
    const first = body.querySelector("[data-document-id]");
    if (pane && wanted) open(wanted);
    else if (pane && first && window.matchMedia("(min-width: 992px)").matches) open(first.dataset.documentId);
    // The shipment on screen follows a change made elsewhere.
    onRealtime(["sales_document"], (detail) => {
        if (pane?.shownId && (detail.kind === "resync" || String(detail.id) === pane.shownId)) pane.refresh();
    });
    const dialog = document.getElementById("create-sales-document-dialog");
    if (!dialog) return;
    const createForm = document.getElementById("create-sales-document-form");
    const customerSelect = document.getElementById("create-sales-document-customer");
    const saleSelect = document.getElementById("create-sales-document-sale");
    function renderSalesDocumentReview() {
        renderWizardReview(document.getElementById("create-sales-document-review"), [
            ["مشتری", selectedOptionText(customerSelect)],
            ["فروش مرتبط", selectedOptionText(saleSelect)],
            ["شماره داخلی سند", document.getElementById("create-sales-document-number").value],
            ["وضعیت پستی آغازین", selectedOptionText(document.getElementById("create-sales-document-status"))],
            ["یادداشت", document.getElementById("create-sales-document-notes").value || "—"],
        ]);
    }
    const salesDocumentWizard = setupWizard(dialog, {onReachLastStep: renderSalesDocumentReview});
    document.getElementById("open-create-sales-document").addEventListener("click", () => {
        createForm.reset();
        clearMessages(createForm);
        salesDocumentWizard?.goFirst();
        dialog.showModal();
    });
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    let sales = [];
    try {
        const [customers, loadedSales] = await Promise.all([
            loadAllPages("/api/v1/customers/?ordering=full_name"),
            loadAllPages("/api/v1/sales/?ordering=-sold_at"),
            // No empty option: a parcel that has just been registered is
            // in the shop's own store, which is the first state, so the
            // default is a fact rather than a prompt.
            fillPostalStates(document.getElementById("create-sales-document-status")),
        ]);
        sales = loadedSales;
        fillSelect(customerSelect, customers, (customer) => customer.full_name, "یک مشتری انتخاب کنید");
    } catch (error) { showError(error); }
    function refreshSales() {
        const customerId = Number(customerSelect.value);
        fillSelect(saleSelect, sales.filter((sale) => Number(sale.customer) === customerId), (sale) => `فروش ${sale.id} — ${sale.product_name || sale.product}`, "بدون فروش مرتبط");
    }
    customerSelect.addEventListener("change", refreshSales);
    createForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(createForm, async () => {
            const payload = formPayload(createForm, ["customer", "sale", "document_number", "postal_status", "notes"]);
            if (!payload.sale) delete payload.sale;
            const item = await apiRequest(createForm.action, {method: "POST", body: payload});
            window.location.assign(`/sales-documents/${item.id}/`);
        });
    });
}
