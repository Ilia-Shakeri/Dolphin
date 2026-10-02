import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDate, displayDate, displayDay} from "dolphin/core/jalali.js";
import {DOCUMENT_STATUS_TEXT, SETTLEMENT_TEXT} from "dolphin/core/labels.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money, moneyToStorage} from "dolphin/core/money.js";
import {INSTALLMENT_DISPLAY_ACCENT, documentLineEditor} from "dolphin/features/billing/shared.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {setupInvoiceCampaign} from "dolphin/ui/invoice-campaign.js";
import {setupInvoiceFulfillment} from "dolphin/ui/invoice-fulfillment.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {appendCell, appendMoneyCell, labelled} from "dolphin/ui/table.js";

/**
 * A stored calendar day, for a `data-jalali="date"` input.
 *
 * `localDateValue` below reads an instant and drops its clock. This reads a
 * day that never had one — `document_date` is a `DateField` and arrives as a
 * bare `YYYY-MM-DD`. Putting that through the instant path would send it
 * through a time zone and could land on the day before.
 */
function localDayValue(value) {
    const shown = displayDay(value);
    return shown === "—" ? "" : shown;
}

/**
 * What this invoice still lacks before it can be issued as official.
 *
 * The server decides this - `official_invoice_identity_errors` in
 * billing/services.py refuses the issue - and this only mirrors the same
 * conditions so the operator learns before pressing the button rather than
 * after. It is a convenience, never the check: an invoice that got past
 * this list is still refused by the service if it is genuinely incomplete.
 */
function officialInvoiceChecklist(invoice) {
    const missing = [];
    if (!invoice.customer_national_id) {
        missing.push("کد/شناسه ملی خریدار در پروندهٔ مشتری");
    }
    if (invoice.customer_kind === "legal" && !invoice.customer_economic_code) {
        missing.push("شماره اقتصادی خریدار (مشتری حقوقی)");
    }
    return missing;
}

function syncOfficialInvoiceNotice(invoice) {
    const notice = document.getElementById("invoice-official-requirements");
    const list = document.getElementById("invoice-official-checklist");
    const select = document.getElementById("edit-invoice-type");
    if (!notice || !list || !select) return;
    if (select.value !== "official") {
        notice.hidden = true;
        return;
    }
    const missing = officialInvoiceChecklist(invoice || {});
    list.textContent = missing.length
        ? `این موارد هنوز ثبت نشده‌اند: ${missing.join("، ")}`
        : "هویت‌های لازم کامل است. هویت فروشنده از تنظیمات استقرار خوانده می‌شود و هنگام صدور بررسی می‌شود.";
    notice.hidden = false;
}

export async function setupInvoiceDetail() {
    const invoiceId = document.body.dataset.invoiceId;
    const endpoint = `/api/v1/invoices/${invoiceId}/`;
    const loading = document.getElementById("invoice-detail-loading");
    const content = document.getElementById("invoice-detail-content");
    const statusSelect = document.getElementById("invoice-status-select");
    const paidInput = document.getElementById("invoice-paid");
    const allocationsSection = document.getElementById("invoice-allocations");
    const form = document.getElementById("edit-invoice-form");
    const editActions = document.getElementById("invoice-edit-actions");
    const lockedNote = document.getElementById("invoice-locked-note");
    const issuedNote = document.getElementById("invoice-issued-note");
    const lines = documentLineEditor({doc: "invoice", endpoint, onSaved: (updated) => apply(updated)});
    let allocationsController = null;

    let current = null;

    function apply(invoice, installments = null) {
        current = invoice;
        document.getElementById("invoice-number").value = invoice.number;
        document.getElementById("invoice-customer").value = invoice.customer_name;
        if (statusSelect) {
            statusSelect.value = invoice.status;
        } else {
            document.getElementById("invoice-status").value = labelled(DOCUMENT_STATUS_TEXT, invoice.status);
        }
        // Settlement is derived and read-only for everyone.
        document.getElementById("invoice-settlement").value = labelled(SETTLEMENT_TEXT, invoice.settlement_status);
        // Editable only while the invoice is a draft: after issue the type is
        // part of what was issued, and the service refuses to change it.
        const typeSelect = document.getElementById("edit-invoice-type");
        if (typeSelect) {
            typeSelect.value = invoice.invoice_type || "unofficial";
            typeSelect.disabled = invoice.status !== "draft";
        }
        syncOfficialInvoiceNotice(invoice);
        document.getElementById("edit-invoice-document-date").value =
            localDayValue(invoice.document_date);
        document.getElementById("invoice-issued-at").value = displayDay(invoice.issued_at);
        // Derived, and shown as such. It is the sum of the allocations made
        // against this invoice from the receipts desk; «مانده» follows it.
        if (paidInput) paidInput.value = money(invoice.paid_amount);
        document.getElementById("invoice-balance").value = money(invoice.balance_due);
        document.getElementById("edit-invoice-notes").value = invoice.notes || "";
        const editable = invoice.status === "draft";
        // Issued and correctable are not the same thing: an issued invoice
        // can still have its note corrected, so the save action stays
        // available and only the note field itself is enabled — everything
        // that could move money or the document's legal shape stays locked.
        const noteOnly = invoice.status === "issued";
        if (editActions) editActions.hidden = !(editable || noteOnly);
        if (issuedNote) issuedNote.hidden = !noteOnly;
        if (lockedNote) lockedNote.hidden = editable || noteOnly;
        form.querySelectorAll("input[name], textarea[name]").forEach((field) => {
            field.disabled = noteOnly ? field.name !== "notes" : !editable;
        });
        if (allocationsSection) allocationsSection.hidden = invoice.status !== "issued";
        if (invoice.status === "issued") allocationsController?.load();
        if (installments) renderInstallments(installments);
        else loadInstallments();
        lines.apply(invoice);
    }

    const installmentsSection = document.getElementById("invoice-installments");
    const installmentsBody = document.getElementById("invoice-installments-body");
    const installmentsDown = document.getElementById("invoice-installments-down");
    const installmentsCount = document.getElementById("invoice-installments-count");
    const canEditIssuedInstallments = installmentsSection?.dataset.canPayments === "1";
    let installmentsSummary = null;

    // A draft has no rows yet: they are worked out here from the same rule
    // the server applies at issue (down payment first, the remainder in
    // equal parts, the rounding remainder on the first one) so the box
    // reads the same before and after issuing.
    function draftInstallmentRows(summary) {
        const total = Number(current?.total_amount);
        const count = Number(summary.installment_count);
        if (!(total > 0) || !(count >= 1)) return [];
        const down = Number(summary.down_payment) || 0;
        const remainder = Math.round((total - down) * 100);
        const base = Math.round(remainder / count);
        const first = remainder - base * (count - 1);
        const rows = [];
        if (down > 0) {
            rows.push({is_down_payment: true, sequence: 0, due_date: null, amount: down.toFixed(2), paid_amount: "0.00", balance_due: down.toFixed(2), status: "pending", status_display: "در انتظار پرداخت"});
        }
        for (let index = 0; index < count; index += 1) {
            const cents = index === 0 ? first : base;
            let due = null;
            if (summary.first_due) {
                const day = new Date(`${summary.first_due}T00:00:00Z`);
                day.setUTCDate(day.getUTCDate() + Number(summary.interval_days || 0) * index);
                due = day.toISOString().slice(0, 10);
            }
            rows.push({is_down_payment: false, sequence: index + 1, due_date: due, amount: (cents / 100).toFixed(2), paid_amount: "0.00", balance_due: (cents / 100).toFixed(2), status: "pending", status_display: "در انتظار پرداخت"});
        }
        return rows;
    }

    function renderInstallments(summary) {
        installmentsSummary = summary;
        if (!installmentsSection) return;
        installmentsSection.hidden = !summary || summary.payment_type !== "installment";
        if (installmentsSection.hidden) return;
        const canEdit = summary.editable && (current?.status === "draft" || canEditIssuedInstallments);
        if (installmentsDown) {
            installmentsDown.value = money(summary.down_payment, {withCurrency: false});
            installmentsDown.disabled = !canEdit;
        }
        if (installmentsCount) {
            installmentsCount.value = summary.installment_count ?? "";
            installmentsCount.disabled = !canEdit;
        }
        const rows = summary.rows.length ? summary.rows : draftInstallmentRows(summary);
        installmentsBody.replaceChildren(...rows.map((item) => {
            const row = document.createElement("tr");
            appendCell(row, item.is_down_payment ? "پیش‌پرداخت" : `قسط ${toPersianDigits(item.sequence)}`);
            appendCell(row, item.due_date ? displayDay(item.due_date) : "—");
            appendMoneyCell(row, item.amount);
            appendMoneyCell(row, item.paid_amount);
            appendMoneyCell(row, item.balance_due);
            const cell = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = `badge badge-light-${INSTALLMENT_DISPLAY_ACCENT[item.status] || "secondary"}`;
            badge.textContent = item.status_display;
            cell.append(badge);
            row.append(cell);
            return row;
        }));
    }

    async function loadInstallments() {
        if (!installmentsSection) return;
        if (current?.payment_type !== "installment") {
            installmentsSection.hidden = true;
            return;
        }
        try {
            renderInstallments(await apiRequest(`${endpoint}installments/`));
        } catch (error) {
            showError(error);
        }
    }

    async function saveInstallmentTerms() {
        if (!installmentsSummary?.editable) return;
        const count = Number(installmentsCount.value);
        const down = moneyToStorage(installmentsDown.value) || "0";
        if (!Number.isInteger(count) || count < 1) return;
        withSubmit(document.getElementById("invoice-installments-form"), async () => {
            const updated = await apiRequest(`${endpoint}set-installments/`, {
                method: "POST", body: {installment_count: count, down_payment: down},
            });
            globalMessage("اقساط دوباره محاسبه شد.", true);
            current = await apiRequest(endpoint);
            apply(current, updated);
        });
    }

    const installmentsForm = document.getElementById("invoice-installments-form");
    installmentsForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        saveInstallmentTerms();
    });
    [installmentsDown, installmentsCount].forEach((field) =>
        field?.addEventListener("change", () => installmentsForm.requestSubmit())
    );

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const data = new FormData(form);
            // An issued invoice may correct only its note — the server
            // enforces this too, but sending anything else here would fail
            // on a field the reader never touched, since every disabled
            // input still has whatever value it was showing. `due_at` has
            // no field on this form since 1.4.0 and is never sent; sending
            // it as `null` on every save was silently clearing a value nothing
            // on screen offered to change.
            const payload = {notes: String(data.get("notes") || "")};
            if (current?.status !== "issued") {
                // Null when cleared rather than omitted, so an operator can
                // take a wrong date off a draft as well as correct one.
                payload.document_date = apiDate(data.get("document_date"));
                const typeField = document.getElementById("edit-invoice-type");
                if (typeField && !typeField.disabled) payload.invoice_type = typeField.value;
            }
            const updated = await apiRequest(endpoint, {method: "PATCH", body: payload});
            apply(updated);
            globalMessage("سربرگ فاکتور ذخیره شد.", true);
        });
    });

    // The invoice lifecycle runs from the status select. Issuing posts the
    // customer debit and freezes the lines; it moves no stock, because the
    // order already did.
    statusSelect?.addEventListener("change", async () => {
        const next = statusSelect.value;
        if (!current || next === current.status) return;
        const questions = {
            issued: "فاکتور صادر شود؟ پس از صدور، اقلام و مبالغ تغییرناپذیر می‌شوند و بدهکاری مشتری ثبت می‌شود.",
            cancelled: "فاکتور ابطال شود؟ اثر دفتر حساب برگردانده می‌شود.",
        };
        if (!await confirmDialog(questions[next] || "وضعیت فاکتور تغییر کند؟")) {
            statusSelect.value = current.status;
            return;
        }
        statusSelect.disabled = true;
        clearMessages();
        try {
            if (next === "issued") {
                apply(await apiRequest(`${endpoint}issue/`, {method: "POST"}));
                globalMessage("فاکتور صادر شد.", true);
            } else if (next === "cancelled") {
                apply(await apiRequest(`${endpoint}cancel/`, {method: "POST", body: {reason: ""}}));
                globalMessage("فاکتور ابطال شد.", true);
            } else {
                statusSelect.value = current.status;
                globalMessage("بازگشت به پیش‌نویس ممکن نیست.");
            }
        } catch (error) {
            statusSelect.value = current.status;
            showError(error);
        } finally {
            statusSelect.disabled = false;
        }
    });

    document.getElementById("edit-invoice-type")?.addEventListener("change", () => {
        syncOfficialInvoiceNotice(current);
    });

    // No handler for «پرداخت شده» any more, and none for «سفارش».
    //
    // The paid figure used to be typed here and posted to `manual-paid/`,
    // which settled the invoice without writing a Payment, an allocation or
    // a ledger entry — a second source of truth for how much had been paid,
    // and the one with no trail behind it. It is now only ever the sum of
    // the allocations recorded on the receipts desk.

    if (allocationsSection) {
        allocationsController = setupPagedList({
            key: "invoice-allocations",
            form: null,
            endpoint: (page) => `${endpoint}allocations/?page=${page}`,
            renderRow: (allocation) => {
                const row = document.createElement("tr");
                appendCell(row, allocation.payment_number).dir = "ltr";
                appendMoneyCell(row, allocation.amount);
                appendCell(row, allocation.is_reversed ? "آزادشده" : "فعال");
                appendCell(row, allocation.created_by_display || allocation.created_by);
                appendCell(row, displayDate(allocation.created_at));
                return row;
            },
        });
    }

    try {
        const [invoice] = await Promise.all([apiRequest(endpoint), lines.loadProducts()]);
        apply(invoice);
        loading.hidden = true;
        content.hidden = false;
        setupInvoiceCampaign(invoiceId, invoice.status);
        setupInvoiceFulfillment(invoiceId, invoice.status);
    } catch (error) {
        loading.hidden = true;
        showError(error);
    }
}
