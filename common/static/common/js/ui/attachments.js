import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {appendCell} from "dolphin/ui/table.js";
import {removeWithMotion, trashButton} from "dolphin/ui/trash.js";

/**
 * The chart card beneath a list page, wherever one is declared.
 *
 * Driven by `data-list-chart` in the markup rather than by a per-page
 * function, so a twelfth page needs a template card and a registry entry
 * and no JavaScript at all.
 *
 * Every failure is contained to the card. A role without the capability, or
 * a deployment without the module, leaves the list above it working and
 * says so in the space the chart would have taken - a chart is never worth
 * taking a page down for.
 */
/**
 * The attachments panel (common/includes/attachments_panel.inc), reused
 * on all five detail pages that carry one: customer, lead, invoice,
 * sales-document, after-sales. One generic function rather than five
 * near-duplicates — the only thing that varies per page is which parent
 * field the panel names and which of `document.body.dataset` already
 * carries that record's id.
 */
const ATTACHMENTS_PARENT_ID_KEY = {
    customer: "customerId",
    lead: "leadId",
    invoice: "invoiceId",
    sales_document: "salesDocumentId",
    after_sales_request: "afterSalesId",
};

function humanFileSize(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${toPersianDigits(String(value))} بایت`;
    const kb = value / 1024;
    if (kb < 1024) return `${toPersianDigits(kb.toFixed(1))} کیلوبایت`;
    return `${toPersianDigits((kb / 1024).toFixed(1))} مگابایت`;
}

function attachmentRow(panel, item) {
    const row = document.createElement("tr");
    const nameCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = `/api/v1/attachments/${item.id}/download/`;
    link.textContent = item.original_filename;
    link.target = "_blank";
    link.rel = "noopener";
    nameCell.appendChild(link);
    row.appendChild(nameCell);
    [item.content_type, humanFileSize(item.size_bytes), item.uploaded_by_name, displayDate(item.uploaded_at)]
        .forEach((value) => appendCell(row, value));
    const actions = document.createElement("td");
    if (panel.dataset.canDelete === "true") {
        const button = trashButton(`حذف پیوست ${item.original_filename || ""}`.trim());
        button.classList.add("btn-sm");
        button.addEventListener("click", async () => {
            if (!await confirmDialog("این پیوست برای همیشه حذف شود؟")) return;
            try {
                await apiRequest(`/api/v1/attachments/${item.id}/delete/`, {method: "POST"});
                await removeWithMotion(row);
                await loadAttachments(panel);
            } catch (error) {
                showError(error);
            }
        });
        actions.appendChild(button);
    }
    row.appendChild(actions);
    return row;
}

async function loadAttachments(panel) {
    const field = panel.dataset.attachmentsField;
    const parentId = document.body.dataset[ATTACHMENTS_PARENT_ID_KEY[field]];
    const empty = panel.querySelector("[data-attachments-empty]");
    const wrap = panel.querySelector("[data-attachments-table-wrap]");
    const body = panel.querySelector("[data-attachments-table-body]");
    try {
        const items = await apiRequest(`/api/v1/attachments/?${new URLSearchParams({[field]: parentId})}`);
        const rows = items.map((item) => attachmentRow(panel, item));
        body.replaceChildren(...rows);
        empty.hidden = Boolean(rows.length);
        wrap.hidden = !rows.length;
    } catch (error) {
        showError(error);
    }
}

/**
 * Refuse a file the server was always going to refuse, before sending it.
 *
 * Both limits are read off the panel's own data attributes, which
 * `attachments_panel.inc` renders from `attachments/` itself
 * (`common/templatetags/attachment_tags.py`) — never hard-coded here, so
 * the sentence printed above the form, the check below, and the rule the
 * server enforces are one value in three places rather than three values
 * (product-owner request 2026-09-19).
 *
 * This is a courtesy, not a control: the server still sniffs the real
 * bytes and still enforces the ceiling. Sending ten megabytes over a slow
 * connection only to be told it was never allowed is what this saves.
 * Returns a reason string, or an empty string when the file is fine.
 */
function attachmentRejectionReason(panel, file) {
    const maxBytes = Number(panel.dataset.attachmentsMaxBytes);
    const accept = (panel.dataset.attachmentsAccept || "")
        .split(",").map((one) => one.trim()).filter(Boolean);
    // `file.type` is the browser's own guess and can be empty; an empty
    // guess is passed through to the server, which decides from the bytes.
    if (accept.length && file.type && !accept.includes(file.type)) {
        return "قالب این فایل پذیرفته نمی‌شود. یکی از قالب‌های مجاز بالا را انتخاب کنید.";
    }
    if (Number.isFinite(maxBytes) && maxBytes > 0 && file.size > maxBytes) {
        const limit = toPersianDigits(String(Math.round(maxBytes / (1024 * 1024))));
        const actual = toPersianDigits((file.size / (1024 * 1024)).toFixed(1));
        return `حجم این فایل ${actual} مگابایت است و از سقف ${limit} مگابایت بیشتر است.`;
    }
    return "";
}

/**
 * Every attachments panel on the page — except one inside a profile tab,
 * which its tab wires up the first time it opens (2.19.0), so a profile
 * does not fetch its documents until someone looks at them.
 */
export function setupAttachmentsPanel() {
    document.querySelectorAll("[data-attachments-panel]").forEach((panel) => {
        if (panel.closest("[data-profile-pane]")) return;
        setupAttachmentsPanelFor(panel);
    });
}

export function setupAttachmentsPanelFor(panel) {
    if (panel.dataset.attachmentsReady) return;
    panel.dataset.attachmentsReady = "true";
    loadAttachments(panel);
    const form = panel.querySelector("[data-attachments-upload-form]");
    if (!form) return;
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const field = panel.dataset.attachmentsField;
            const parentId = document.body.dataset[ATTACHMENTS_PARENT_ID_KEY[field]];
            const input = form.querySelector("[data-attachments-file]");
            const file = input.files[0];
            if (!file) return;
            const reason = attachmentRejectionReason(panel, file);
            if (reason) {
                const slot = form.querySelector('[data-error-for="file"]');
                if (slot) slot.textContent = reason;
                globalMessage(reason);
                input.focus();
                return;
            }
            const payload = new FormData();
            payload.set("file", file);
            payload.set(field, parentId);
            await apiRequest("/api/v1/attachments/", {method: "POST", body: payload, raw: true});
            form.reset();
            await loadAttachments(panel);
        });
    });
}
