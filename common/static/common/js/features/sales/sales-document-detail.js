import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {fillPostalStates, postalBadge} from "dolphin/features/sales/shared.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {loadAllPages} from "dolphin/ui/lists.js";
import {appendCell} from "dolphin/ui/table.js";

/**
 * The four postal stops, drawn side by side with the current one lit.
 *
 * The stops come from the server (`postal_stepper`) rather than from a
 * table here: `sales/postal.py` owns which states exist, what they are
 * called, what icon each carries and what order they travel in, and a
 * second copy of that in the panel is the copy that goes stale the day a
 * state is added.
 *
 * A document whose status is free text — anything registered before the
 * vocabulary existed — gets an empty list and this card stays hidden.
 * Drawing four stops with none of them current would say something false
 * about where the parcel is; the stored text is still shown in the
 * «وضعیت پستی جاری» field above.
 */
function renderPostalStepper(steps, badge) {
    const card = document.getElementById("postal-stepper-card");
    const list = document.getElementById("postal-stepper");
    if (!card || !list) return;
    // The post office's own status, with its icon (2.40.26); for a status
    // outside the four stages the card shows it alone.
    const slot = document.getElementById("postal-badge-slot");
    const node = postalBadge(badge);
    if (slot) slot.replaceChildren(...(node ? [node] : []));
    if (!steps || !steps.length) {
        card.hidden = !node;
        list.replaceChildren();
        return;
    }
    list.replaceChildren(...steps.map((step, index) => {
        const item = document.createElement("li");
        item.className = `postal-step postal-step-${step.stage}`;
        item.dataset.postalStep = step.key;
        // The stage is announced, not only coloured: «مرحلهٔ جاری» is
        // the one thing a screen reader has to be told, since the ring
        // and the accent say it to everybody else.
        if (step.stage === "current") item.setAttribute("aria-current", "step");

        const mark = document.createElement("span");
        mark.className = "postal-step-mark";
        const icon = document.createElement("i");
        icon.className = `di-duotone ${step.icon} fs-2`;
        for (let path = 1; path <= (step.icon_paths || 2); path += 1) {
            const span = document.createElement("span");
            span.className = `path${path}`;
            icon.append(span);
        }
        mark.append(icon);

        const body = document.createElement("span");
        body.className = "postal-step-body";
        const label = document.createElement("span");
        label.className = "postal-step-label";
        label.textContent = `${toPersianDigits(String(index + 1))}. ${step.label}`;
        const note = document.createElement("span");
        note.className = "postal-step-note";
        note.textContent = step.description;
        body.append(label, note);

        item.append(mark, body);
        return item;
    }));
    card.hidden = false;
}

function fillSalesDocument(item) {
    document.getElementById("sales-document-number").value = item.document_number;
    document.getElementById("sales-document-customer").value = item.customer_name || item.customer;
    document.getElementById("sales-document-sale").value = item.sale || "—";
    document.getElementById("sales-document-registered-by").value = item.registered_by_display || item.registered_by;
    document.getElementById("sales-document-province").value = item.province_snapshot || "—";
    document.getElementById("sales-document-city").value = item.city_snapshot || "—";
    document.getElementById("sales-document-postal-code").value = item.postal_code_snapshot || "—";
    document.getElementById("sales-document-address").value = item.address_snapshot || "—";
    // The state's own Persian label, not its stored key — and for a row
    // written before the vocabulary, the text the operator typed.
    document.getElementById("sales-document-status").value =
        item.postal_status_display || item.postal_status;
    renderPostalStepper(item.postal_stepper, item.postal_badge);
    document.getElementById("sales-document-notes").value = item.notes || "";
    document.getElementById("sales-document-active-state").textContent = item.is_active ? "سند فعال است." : "سند غیرفعال است؛ تاریخچه حفظ شده است.";
    const section = document.getElementById("postal-transition-section");
    if (section) section.hidden = !item.is_active;
}

/** One history cell: the state's own icon (`sales.postal.POSTAL_STATES`)
 * beside its label, or the label alone for free text from before the
 * vocabulary. The icon is decorative; the label is the text. */
function statusCell(label, icon) {
    const cell = document.createElement("td");
    const wrap = document.createElement("span");
    wrap.className = "d-inline-flex align-items-center gap-2";
    if (icon && icon.icon) {
        const glyph = document.createElement("i");
        glyph.className = `di-duotone ${icon.icon} fs-4 text-primary`;
        glyph.setAttribute("aria-hidden", "true");
        for (let path = 1; path <= (icon.icon_paths || 2); path += 1) {
            const span = document.createElement("span");
            span.className = `path${path}`;
            glyph.append(span);
        }
        wrap.append(glyph);
    }
    const text = document.createElement("span");
    text.textContent = label;
    wrap.append(text);
    cell.append(wrap);
    return cell;
}

async function loadPostalHistory(id) {
    const loading = document.getElementById("postal-history-loading");
    const empty = document.getElementById("postal-history-empty");
    const wrap = document.getElementById("postal-history-table-wrap");
    const rows = await loadAllPages(`/api/v1/sales-documents/${id}/postal-history/`);
    const nodes = rows.map((item) => {
        const row = document.createElement("tr");
        row.append(
            statusCell(item.from_status_display || item.from_status || "آغاز", item.from_status_icon),
            statusCell(item.to_status_display || item.to_status, item.to_status_icon),
        );
        [
            item.changed_by_display || item.changed_by,
            item.reason || "—",
            displayDate(item.changed_at),
        ].forEach((value) => appendCell(row, value));
        return row;
    });
    document.getElementById("postal-history-table-body").replaceChildren(...nodes);
    loading.hidden = true; empty.hidden = Boolean(nodes.length); wrap.hidden = !nodes.length;
}

export async function setupSalesDocumentDetail() {
    const id = document.body.dataset.salesDocumentId;
    const endpoint = `/api/v1/sales-documents/${id}/`;
    const loading = document.getElementById("sales-document-detail-loading");
    const content = document.getElementById("sales-document-detail-content");
    let item;
    try {
        [item] = await Promise.all([apiRequest(endpoint), loadPostalHistory(id)]);
        fillSalesDocument(item); loading.hidden = true; content.hidden = false;
    } catch (error) { loading.hidden = true; document.getElementById("postal-history-loading").hidden = true; showError(error); return; }
    // Filled from the same list the stepper is drawn from, so the form
    // can never offer a state the stepper cannot show.
    try {
        await fillPostalStates(document.getElementById("postal-to-status"), {
            emptyLabel: "یک وضعیت انتخاب کنید",
        });
    } catch (error) {
        showError(error);
    }

    const form = document.getElementById("postal-transition-form");
    form?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            item = await apiRequest(form.action, {method: "POST", body: formPayload(form, ["to_status", "reason"])});
            fillSalesDocument(item); form.reset(); await loadPostalHistory(id); globalMessage("وضعیت پستی ثبت شد.", true);
        });
    });
    document.getElementById("deactivate-sales-document")?.addEventListener("click", async () => {
        if (!await confirmDialog("این سند غیرفعال شود؟ تاریخچه پاک نمی‌شود.")) return;
        try { item = await apiRequest(`${endpoint}deactivate/`, {method: "POST"}); fillSalesDocument(item); globalMessage("سند غیرفعال شد.", true); } catch (error) { showError(error); }
    });
}
