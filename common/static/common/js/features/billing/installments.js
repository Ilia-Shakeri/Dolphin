import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDate, displayDay} from "dolphin/core/jalali.js";
import {INSTALLMENT_DISPLAY_ACCENT} from "dolphin/features/billing/shared.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {appendCell, appendMoneyCell} from "dolphin/ui/table.js";

export function setupInstallments() {
    const form = document.getElementById("installment-search-form");
    setupListFilter("installment");
    const controller = setupPagedList({
        key: "installments",
        form,
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const status = document.getElementById("installment-status-filter").value;
            if (status) query.set("status", status);
            const dueBefore = document.getElementById("installment-due-before").value;
            if (dueBefore) query.set("due_before", apiDate(dueBefore));
            query.set("ordering", document.getElementById("installment-ordering").value);
            return `/api/v1/installments/?${query}`;
        },
        renderRow: (installment) => {
            const row = document.createElement("tr");
            appendCell(row, installment.is_down_payment ? "پیش‌پرداخت" : toPersianDigits(installment.sequence));
            appendCell(row, installment.customer_name);
            const invoiceCell = document.createElement("td");
            row.append(invoiceCell);
            const link = document.createElement("a");
            link.href = `/invoices/${installment.invoice}/`;
            link.textContent = installment.invoice_number;
            link.dir = "ltr";
            invoiceCell.append(link);
            appendMoneyCell(row, installment.amount);
            appendCell(row, displayDay(installment.due_date));
            appendMoneyCell(row, installment.paid_amount);
            appendMoneyCell(row, installment.balance_due);
            const statusCell = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = `badge badge-light-${INSTALLMENT_DISPLAY_ACCENT[installment.display_status] || "secondary"}`;
            badge.textContent = installment.display_status_label;
            statusCell.append(badge);
            row.append(statusCell);
            return row;
        },
    });
    controller.load();
}
