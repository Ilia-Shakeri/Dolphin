import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDate, displayDay} from "dolphin/core/jalali.js";
import {DOCUMENT_STATUS_TEXT} from "dolphin/core/labels.js";
import {showError} from "dolphin/core/messages.js";
import {money, moneyToStorage} from "dolphin/core/money.js";
import {EMPTY_LINE_ROWS, createLineItemRows, documentTotals, loadCustomerOptions, renderDocumentTotals, setupDocumentList, validateLinesStep} from "dolphin/features/billing/shared.js";
import {loadAllPages} from "dolphin/ui/lists.js";
import {setupSearchableSelects} from "dolphin/ui/searchable-select.js";
import {appendCell, appendMoneyCell, appendStatusBadgeCell, labelled} from "dolphin/ui/table.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

// وضعیت — one of the two axes a cheque has since 1.3.0. The other, حالت,
// is a yes/no and is rendered by CHEQUE_REGISTRATION_TEXT below.
//: The server sends `invoice_type_display` already translated; this is the
//: fallback for a row that predates it, and the source for the filter's own
//: two options.
const INVOICE_TYPE_TEXT = Object.freeze({
    official: "رسمی",
    unofficial: "غیررسمی",
});

export async function setupInvoices() {
    const lineHost = document.getElementById("create-invoice-lines");
    let lines = EMPTY_LINE_ROWS;
    const dialog = document.getElementById("create-invoice-dialog");
    const wizard = setupWizard(dialog, {
        onReachLastStep: () => renderReview(),
        validateStep: (index, content) => validateLinesStep(content, lines),
    });
    const paymentTypeSelect = document.getElementById("create-invoice-payment-type");
    const installmentReveal = document.getElementById("create-invoice-installment-reveal");
    const installmentFields = document.getElementById("create-invoice-installment-fields");
    // Cash hides the instalment fields *and* switches them off: a disabled field
    // is left out of the submitted form and of validation, so a value typed
    // before changing one's mind can never reach the server.
    const syncPaymentType = () => {
        const installment = paymentTypeSelect?.value === "installment";
        installmentReveal?.classList.toggle("is-open", installment);
        installmentReveal?.toggleAttribute("inert", !installment);
        installmentFields?.querySelectorAll("input, select, textarea").forEach((field) => {
            field.disabled = !installment;
            field.required = installment && field.id !== "create-invoice-down-payment";
        });
        installmentFields?.querySelectorAll("[data-error-for]").forEach((node) => {
            if (!installment) node.textContent = "";
        });
    };
    syncPaymentType();
    paymentTypeSelect?.addEventListener("change", syncPaymentType);

    function renderReview() {
        const totals = documentTotals(
            lines.grossTotals(),
            document.getElementById("create-invoice-discount")?.value,
            document.getElementById("create-invoice-tax")?.value,
        );
        const installment = paymentTypeSelect?.value === "installment";
        const down = Number(moneyToStorage(document.getElementById("create-invoice-down-payment")?.value)) || 0;
        const count = Number(document.getElementById("create-invoice-installment-count")?.value) || 0;
        renderWizardReview(document.getElementById("create-invoice-review"), [
            ["مشتری", selectedOptionText(document.getElementById("create-invoice-customer"))],
            ["نوع فاکتور", selectedOptionText(document.getElementById("create-invoice-type"))],
            ["تاریخ صدور", document.getElementById("create-invoice-document-date")?.value || "روز صدور"],
            // How many different products, not how many units — the
            // count is of rows (2.25.1, product owner's wording).
            ["تنوع محصول", toPersianDigits(String(lines.count()))],
            ["جمع اقلام", money(totals.gross)],
            ["تخفیف", money(totals.discount)],
            ["مالیات", money(totals.tax)],
            ["نوع پرداخت", selectedOptionText(paymentTypeSelect)],
            ...(installment
                ? [
                    ["پیش‌پرداخت", money(down)],
                    ["تعداد اقساط", toPersianDigits(String(count))],
                    ["مبلغ هر قسط", count ? money((totals.total - down) / count) : "—"],
                    ["تاریخ اولین قسط", document.getElementById("create-invoice-first-due")?.value || "—"],
                    ["فاصله اقساط", `${toPersianDigits(document.getElementById("create-invoice-interval-days")?.value || "")} روز`],
                ]
                : []),
            // The figure this wizard is actually about, last and by name.
            ["مبلغ نهایی", money(totals.total)],
        ]);
    }

    const redrawTotals = () => renderDocumentTotals("create-invoice", lines);
    try {
        const [, products] = await Promise.all([
            loadCustomerOptions(document.getElementById("create-invoice-customer"), "یک مشتری انتخاب کنید"),
            loadAllPages("/api/v1/products/?is_active=true&ordering=name"),
        ]);
        lines = createLineItemRows(lineHost, products, {onChange: redrawTotals});
        setupSearchableSelects(dialog);
        lines.addLine();
    } catch (error) {
        showError(error);
    }
    // The two percentages live in the summary now, beside the figures
    // they change, so they redraw it themselves.
    ["create-invoice-discount", "create-invoice-tax"].forEach((id) => {
        document.getElementById(id)?.addEventListener("input", redrawTotals);
    });
    document.getElementById("create-invoice-add-line")?.addEventListener("click", () => {
        lines.addLine();
        redrawTotals();
    });
    setupDocumentList({
        key: "invoices",
        prefix: "invoice",
        detailPath: "/invoices/",
        onOpen: () => {
            document.getElementById("create-invoice-form")?.reset();
            syncPaymentType();
            lines.reset();
            renderDocumentTotals("create-invoice", lines);
            wizard?.goFirst();
        },
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("invoice-search").value.trim();
            if (search) query.set("search", search);
            const status = document.getElementById("invoice-status-filter").value;
            if (status) query.set("status", status);
            const settlement = document.getElementById("invoice-settlement-filter").value;
            if (settlement) query.set("settlement", settlement);
            const invoiceType = document.getElementById("invoice-type-filter").value;
            if (invoiceType) query.set("invoice_type", invoiceType);
            query.set("ordering", document.getElementById("invoice-ordering").value);
            return `/api/v1/invoices/?${query}`;
        },
        columns: [
            // Every value column is centred; the action column is not.
            (row, item) => {
                const cell = appendCell(row, item.number);
                cell.dir = "ltr";
                cell.classList.add("text-center");
            },
            (row, item) => appendCell(row, item.customer_name).classList.add("text-center"),
            (row, item) => appendCell(row, item.campaign_name || "—").classList.add("text-center"),
            (row, item) => appendCell(row, item.created_by_display || "—").classList.add("text-center"),
            (row, item) => appendStatusBadgeCell(row, DOCUMENT_STATUS_TEXT, item.status).classList.add("text-center"),
            (row, item) => appendMoneyCell(row, item.total_amount).classList.add("text-center"),
            (row, item) => appendMoneyCell(row, item.paid_amount).classList.add("text-center"),
            (row, item) => appendMoneyCell(row, item.balance_due).classList.add("text-center"),
            // The date written on the document. Rows from before this field
            // existed have none, so the issue timestamp stands in rather
            // than leaving the column blank.
            (row, item) =>
                appendCell(
                    row,
                    displayDay(item.document_date || item.issued_at),
                ).classList.add("text-center"),
            // Was the due date, which this product never sets — a column of
            // dashes. Whether an invoice is official is what a reader
            // actually needs beside it, and it is also what the new filter
            // narrows by.
            (row, item) =>
                appendCell(
                    row,
                    item.invoice_type_display || labelled(INVOICE_TYPE_TEXT, item.invoice_type),
                ).classList.add("text-center"),
        ],
        createFields: (data) => {
            // No warehouse: an invoice moves no stock, so naming one would
            // suggest an effect it does not have.
            const discountPercent = Number(data.get("discount_percent")) || 0;
            const body = {
                customer: Number(data.get("customer")),
                invoice_type: String(data.get("invoice_type") || "unofficial"),
                tax_rate: Number(data.get("tax_rate")) || 0,
                // The document's own discount (2.26.0, product owner): one
                // percentage of the whole invoice, stored on it and shown
                // in «جمع سند» — not copied onto every line, which is what
                // made each row of «اقلام سند» carry its own discount.
                discount_percent: discountPercent,
                items: lines.collect(),
            };
            // The date on the document, if the operator wrote one. Left out
            // rather than sent empty when they did not, because issuing
            // fills it from the day it was issued.
            const documentDate = apiDate(data.get("document_date"));
            if (documentDate) body.document_date = documentDate;
            if (data.get("payment_type") === "installment") {
                body.payment_type = "installment";
                body.installment_down_payment = moneyToStorage(data.get("installment_down_payment")) || "0";
                body.installment_count = Number(data.get("installment_count"));
                body.installment_first_due = apiDate(data.get("installment_first_due"));
                body.installment_interval_days = Number(data.get("installment_interval_days"));
            }
            return body;
        },
    });
}
