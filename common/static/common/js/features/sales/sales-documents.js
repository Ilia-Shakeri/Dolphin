import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDay} from "dolphin/core/jalali.js";
import {clearMessages, formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {setupPostalPane} from "dolphin/features/sales/postal-pane.js";
import {fillPostalStates, postalBadge} from "dolphin/features/sales/shared.js";
import {onRealtime} from "dolphin/ui/realtime.js";
import {fillSelect, loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
import {guardDirtyDialog} from "dolphin/ui/dialogs.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

/**
 * The four postal stops as one connected rail inside the card's status box —
 * the row version of `renderPostalStepper`'s own card.
 *
 * Product owner, 2026-09-21: «وضعیت پستی باید ۴ تا ایکون پست سرهم به هم
 * متصل باشد و در هر مرحله‌ای است باید این ایکون روشن باشد». The list
 * this belongs to is «رهگیری پستی» (`sales_documents/list.html`) — a
 * list of documents, not one document's own page — so each card gets
 * the compact form. Since the 2.40.56 redesign the four marks sit on a
 * single rail that fills up to the stage the parcel has reached, with each
 * stop named underneath; connected is now literally one line rather than
 * four marks touching. `item.postal_stepper` is the same four-entry list
 * `SalesDocumentSerializer` already computes from `sales/postal.py` for the
 * detail page; nothing about the states, their order or their icons is
 * repeated here.
 *
 * A document whose stored status predates the vocabulary (free text), or
 * whose post-office status is outside the four stages (a return, a seizure),
 * gets an empty `postal_stepper` from the server, and this falls back to that
 * status alone — the same choice `renderPostalStepper` makes for the same
 * reason: four marks with none of them current would claim to know where the
 * parcel is when nobody does.
 */
function postalStatusCell(row, item, cell = document.createElement("td")) {
    const steps = item.postal_stepper;
    // The post office's own status, with its icon, above the rail
    // (2.40.26) — and alone for a status outside the four stages, which
    // the stepper cannot place.
    const badge = postalBadge(item.postal_badge);
    const head = document.createElement("div");
    head.className = "postal-card-status-head";
    const caption = document.createElement("span");
    caption.className = "postal-card-status-caption";
    caption.textContent = "مسیر مرسوله";
    head.append(caption);
    if (badge) head.append(badge);
    else {
        const plain = document.createElement("span");
        plain.className = "postal-card-status-plain";
        plain.textContent = item.postal_status_display || item.postal_status || "—";
        head.append(plain);
    }
    cell.append(head);
    if (!steps || !steps.length) {
        const note = document.createElement("span");
        note.className = "postal-card-status-note";
        note.textContent = "بیرون از چهار مرحلهٔ ارسال";
        cell.append(note);
        row.appendChild(cell);
        return;
    }
    const list = document.createElement("ul");
    list.className = "postal-mini-stepper";
    const current = steps.find((step) => step.stage === "current");
    list.setAttribute("aria-label", `وضعیت پستی: ${current ? current.label : item.postal_status_display || ""}`);
    // How far the rail is filled: the share of the way from the first mark to
    // the last that the parcel has actually travelled — the current stage's
    // own place in the server's list, never a count of anything drawn here.
    const reached = current ? steps.indexOf(current) : steps.filter((step) => step.stage === "done").length - 1;
    const travelled = steps.length > 1 ? Math.max(reached, 0) / (steps.length - 1) : 0;
    list.style.setProperty("--postal-progress", `${(travelled * 100).toFixed(2)}%`);
    list.style.setProperty("--postal-stops", String(steps.length));
    const rail = document.createElement("li");
    rail.className = "postal-mini-rail";
    rail.setAttribute("aria-hidden", "true");
    rail.appendChild(document.createElement("span")).className = "postal-mini-rail-fill";
    list.append(rail);
    list.append(...steps.map((step) => {
        const mark = document.createElement("li");
        mark.className = `postal-mini-step postal-mini-step-${step.stage}`;
        mark.title = step.label;
        const dot = document.createElement("span");
        dot.className = "postal-mini-mark";
        const icon = document.createElement("i");
        icon.className = `di-duotone ${step.icon} fs-6`;
        for (let path = 1; path <= (step.icon_paths || 2); path += 1) {
            icon.appendChild(document.createElement("span")).className = `path${path}`;
        }
        dot.append(icon);
        const label = document.createElement("span");
        label.className = "postal-mini-label";
        label.textContent = step.label;
        mark.append(dot, label);
        return mark;
    }));
    cell.append(list);
    row.appendChild(cell);
}

/**
 * One shipment as a card in the list pane (2.40.34, redrawn 2.40.56): the
 * number and the day it was registered on top, then the customer with the
 * place the parcel is going to, then a boxed status line with the post
 * office's own word and the four stages. The whole card opens the shipment in
 * the pane beside it; a real link inside keeps «open in a new tab» working.
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
    const when = document.createElement("span");
    when.className = "postal-list-date";
    when.textContent = displayDay(item.registered_at);
    top.append(link, when);
    const customer = document.createElement("div");
    customer.className = "postal-list-customer";
    // The first letter of the name the server sent, not a picture: a
    // customer has no avatar in this product, and a placeholder face would
    // be decoration pretending to be a record.
    const avatar = document.createElement("span");
    avatar.className = "postal-list-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = (item.customer_name || "—").trim().charAt(0) || "—";
    const names = document.createElement("div");
    names.className = "postal-list-names";
    const name = document.createElement("strong");
    name.className = "postal-list-name";
    name.textContent = item.customer_name || "—";
    const place = document.createElement("span");
    place.className = "postal-list-place";
    const pin = document.createElement("i");
    pin.className = "di-duotone di-geolocation fs-8";
    pin.setAttribute("aria-hidden", "true");
    pin.appendChild(document.createElement("span")).className = "path1";
    pin.appendChild(document.createElement("span")).className = "path2";
    place.append(pin, document.createTextNode(
        [item.province_snapshot, item.city_snapshot].filter(Boolean).join(" / ") || "بدون نشانی"
    ));
    names.append(name, place);
    customer.append(avatar, names);
    const status = document.createElement("div");
    status.className = "postal-list-status";
    postalStatusCell(row, item, status);
    card.append(top, customer, status);
    cell.append(card);
    row.append(cell);
    return row;
}

/**
 * The four stages as chips above the list (2.40.56) — a shortcut to the
 * «وضعیت پستی» selector inside the filter panel, not a second filter: a chip
 * writes its value into that same field and reloads, so the vocabulary stays
 * declared once (`sales/postal.py`, read through `fillPostalStates`) and the
 * server applies the same narrowing it always did. A status chosen in the
 * panel that no chip names (one of the post office's own) simply leaves every
 * chip unlit rather than lying about what is being shown.
 */
function setupStageChips(statusSelect, reload) {
    const host = document.getElementById("sales-documents-stage-chips");
    if (!host || !statusSelect) return () => {};
    // `fillPostalStates` writes the stages first and the post office's own
    // statuses second, each in its own `<optgroup>`; the stages are the group
    // these chips are for.
    const group = statusSelect.querySelector("optgroup");
    const stages = group ? Array.from(group.querySelectorAll("option")) : [];
    if (!stages.length) return () => {};
    const chips = [{value: "", label: "همه"}].concat(stages.map((option) => ({value: option.value, label: option.textContent})));
    const buttons = chips.map((chip) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-sm postal-chip";
        button.dataset.stage = chip.value;
        button.textContent = chip.label;
        button.addEventListener("click", () => {
            if (statusSelect.value === chip.value) return;
            statusSelect.value = chip.value;
            reload();
        });
        return button;
    });
    host.replaceChildren(...buttons);
    host.hidden = false;
    return function syncChips() {
        buttons.forEach((button) => {
            const on = button.dataset.stage === statusSelect.value;
            button.classList.toggle("btn-light-primary", on);
            button.classList.toggle("btn-light", !on);
            button.setAttribute("aria-pressed", on ? "true" : "false");
        });
    };
}

/** Why a parcel was left out of a bulk change, in the reader's words. */
const SKIP_REASONS = {
    same_status: "همین حالا در این وضعیت بود",
    inactive: "غیرفعال است",
    not_found: "در دسترس شما نیست",
};

/**
 * «تغییر وضعیت گروهی» (2.40.41, roadmap «اولویت ۱.۵»): the chosen parcels
 * move to one postal status together. The server applies the single-change
 * rule to each and reports the ones it left out; this only asks and tells.
 */
async function setupBulkPostalStatus(controller, refreshPane) {
    const button = document.getElementById("sales-documents-bulk-status");
    const dialog = document.getElementById("bulk-postal-status-dialog");
    if (!button || !dialog || !controller) return;
    const form = document.getElementById("bulk-postal-status-form");
    const select = document.getElementById("bulk-postal-status-select");
    guardDirtyDialog(dialog, form);
    dialog.querySelectorAll("[data-close-dialog]").forEach((close) => close.addEventListener("click", () => dialog.close()));
    try {
        await fillPostalStates(select, {emptyLabel: "یک وضعیت انتخاب کنید"});
    } catch (error) { showError(error); }
    button.addEventListener("click", () => {
        const ids = controller.selection.selectedIds();
        if (!ids.length) return;
        form.reset();
        clearMessages(form);
        document.getElementById("bulk-postal-status-count").textContent = toPersianDigits(String(ids.length));
        dialog.showModal();
    });
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const result = await apiRequest("/api/v1/sales-documents/bulk-transition-postal-status/", {
                method: "POST",
                body: {...formPayload(form, ["to_status", "reason"]), ids: controller.selection.selectedIds()},
            });
            dialog.close();
            controller.selection.resetSelection();
            await controller.load(controller.page, {quiet: true});
            refreshPane();
            const parts = [];
            if (result.changed.length) parts.push(`${toPersianDigits(String(result.changed.length))} مرسوله به وضعیت تازه رفت`);
            const reasons = {};
            result.skipped.forEach((skip) => { reasons[skip.reason] = (reasons[skip.reason] || 0) + 1; });
            Object.entries(reasons).forEach(([reason, count]) => {
                parts.push(`${toPersianDigits(String(count))} مرسوله ${SKIP_REASONS[reason] || "کنار گذاشته شد"}`);
            });
            globalMessage(parts.join(" — ") || "مرسوله‌ای تغییر نکرد.", result.changed.length > 0 && result.skipped.length === 0);
        });
    });
}

/**
 * How many parcels this list holds, said twice (2.40.56): beside its title and
 * in the figure next to the page heading. Both read `count` from the very
 * response the rows came from, so neither can show more than the reader's own
 * scope and filters already allow.
 */
function showCount(data, filtered) {
    const total = Number(data.count);
    const badge = document.getElementById("sales-documents-count");
    const stat = document.getElementById("postal-heading-stat");
    const text = Number.isFinite(total) ? toPersianDigits(String(total)) : "";
    if (badge) {
        badge.textContent = text;
        badge.hidden = !text;
    }
    if (!stat) return;
    if (!text) { stat.hidden = true; return; }
    document.getElementById("postal-heading-count").textContent = `${text} مرسوله`;
    document.getElementById("postal-heading-note").textContent = filtered ? "نتیجهٔ فیلتر کنونی" : "همهٔ مرسوله‌های در دسترس شما";
    stat.hidden = false;
}

export async function setupSalesDocuments() {
    const form = document.getElementById("sales-document-search-form");
    setupListFilter("sales-document");
    const narrowing = ["sales-document-postal-status", "sales-document-province", "sales-document-city", "sales-document-active"];
    let syncChips = () => {};
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
        onLoaded: (data) => {
            const filtered = Boolean(document.getElementById("sales-document-search").value.trim())
                || narrowing.some((id) => document.getElementById(id).value.trim());
            showCount(data, filtered);
            syncChips();
        },
    });
    // Every stage and every Iran Post status (2.40.26), grouped.
    const statusSelect = document.getElementById("sales-document-postal-status");
    try {
        await fillPostalStates(statusSelect, {emptyLabel: "همهٔ وضعیت‌ها"});
        syncChips = setupStageChips(statusSelect, () => controller.load(1));
        syncChips();
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
    await setupBulkPostalStatus(controller, () => pane?.shownId && pane.refresh());
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
