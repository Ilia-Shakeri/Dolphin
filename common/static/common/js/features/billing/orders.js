import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDateTime, displayDay} from "dolphin/core/jalali.js";
import {DOCUMENT_STATUS_TEXT} from "dolphin/core/labels.js";
import {showError} from "dolphin/core/messages.js";
import {money, textOrNull} from "dolphin/core/money.js";
import {EMPTY_LINE_ROWS, createLineItemRows, loadCustomerOptions, numberOrNull, renderDocumentTotals, setupDocumentList, validateLinesStep} from "dolphin/features/billing/shared.js";
import {setupSupplyBatch} from "dolphin/features/billing/supply-batch.js";
import {loadAllPages} from "dolphin/ui/lists.js";
import {loadWarehouseOptions, setupSearchableSelects} from "dolphin/ui/searchable-select.js";
import {appendCell, appendMoneyCell, appendStatusBadgeCell} from "dolphin/ui/table.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

export async function setupOrders() {
    setupSupplyBatch();
    const lineHost = document.getElementById("create-order-lines");
    const redrawTotals = () => renderDocumentTotals("create-order", lines);
    // Replaced once the catalogue arrives below; a no-op stub means an
    // impatient click on "افزودن کالا" before then does nothing instead
    // of throwing.
    let lines = EMPTY_LINE_ROWS;
    const dialog = document.getElementById("create-order-dialog");
    const wizard = setupWizard(dialog, {
        onReachLastStep: () => renderReview(),
        validateStep: (index, content) => validateLinesStep(content, lines),
    });

    function renderReview() {
        renderWizardReview(document.getElementById("create-order-review"), [
            ["مشتری", selectedOptionText(document.getElementById("create-order-customer"))],
            ["انبار", selectedOptionText(document.getElementById("create-order-warehouse"))],
            ["روش ارسال", selectedOptionText(document.getElementById("create-order-shipping"))],
            ["تاریخ ارسال", document.getElementById("create-order-delivery")?.value || "تعیین نشده"],
            // How many different products, not how many rows (2.40.33, product
            // owner: «تعداد اقلام باید به تنوع محصولات تبدیل شود»).
            ["تنوع محصولات", toPersianDigits(String(new Set(lines.collect().map((line) => line.product).filter(Boolean)).size))],
            ["جمع اقلام", money(lines.grossTotals().reduce((sum, line) => sum + line, 0))],
            // The form collects «توضیحات» and the review never showed it —
            // found by auditing every wizard's review against its own form
            // (2026-09-19). A review step whose job is to reflect what is
            // about to be sent has to show all of it.
            ["توضیحات", document.getElementById("create-order-notes")?.value || "—"],
        ]);
    }

    try {
        const [, , products] = await Promise.all([
            loadCustomerOptions(document.getElementById("create-order-customer"), "یک مشتری انتخاب کنید"),
            // The order names the warehouse its goods leave from on approval.
            loadWarehouseOptions(document.getElementById("create-order-warehouse"), "بدون اثر انبار"),
            loadAllPages("/api/v1/products/?is_active=true&ordering=name"),
        ]);
        lines = createLineItemRows(lineHost, products, {onChange: redrawTotals});
        setupSearchableSelects(dialog);
        lines.addLine();
    } catch (error) {
        showError(error);
    }
    document.getElementById("create-order-add-line")?.addEventListener("click", () => {
        lines.addLine();
        redrawTotals();
    });
    setupDocumentList({
        key: "orders",
        prefix: "order",
        detailPath: "/orders/",
        onOpen: () => {
            document.getElementById("create-order-form")?.reset();
            lines.reset();
            renderDocumentTotals("create-order", lines);
            wizard?.goFirst();
        },
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("order-search").value.trim();
            if (search) query.set("search", search);
            const status = document.getElementById("order-status-filter").value;
            if (status) query.set("status", status);
            query.set("ordering", document.getElementById("order-ordering").value);
            return `/api/v1/orders/?${query}`;
        },
        columns: [
            (row, item) => {
                // The order number, centred like the amount beside it.
                const cell = appendCell(row, item.number);
                cell.dir = "ltr";
                cell.classList.add("text-center");
            },
            (row, item) => appendCell(row, item.customer_name),
            (row, item) => appendStatusBadgeCell(row, DOCUMENT_STATUS_TEXT, item.status),
            (row, item) => appendMoneyCell(row, item.total_amount).classList.add("text-center"),
            // Registration is server-generated and immutable; delivery is
            // the date the operator sets on the order.
            (row, item) => appendCell(row, displayDay(item.created_at)),
            (row, item) => appendCell(row, displayDay(item.expected_delivery_at)),
            (row, item) => appendCell(row, item.created_by_display || item.created_by),
        ],
        createFields: (data) => {
            const payload = {
                customer: Number(data.get("customer")),
                items: lines.collect(),
                notes: String(data.get("notes") || ""),
                shipping_method: String(data.get("shipping_method") || ""),
            };
            const warehouse = numberOrNull(data.get("warehouse"));
            if (warehouse !== null) payload.warehouse = warehouse;
            payload.expected_delivery_at = apiDateTime(textOrNull(data.get("expected_delivery_at")));
            return payload;
        },
    });
}
