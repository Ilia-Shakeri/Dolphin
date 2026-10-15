import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDay} from "dolphin/core/jalali.js";
import {globalMessage, showError} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {appendCell, appendMoneyCell} from "dolphin/ui/table.js";

/**
 * A receipt and instalment charges (2.40.52): the customer's open interest
 * and late fees, settled from this receipt one by one or all at once
 * (earliest due first), and what this receipt has settled, each releasable.
 * Every rule is `billing.installment_charges`.
 */
const persian = (text) => String(text).replace(/\d+/g, (digits) => toPersianDigits(digits));

export function setupPaymentCharges({endpoint, onChanged}) {
    const section = document.getElementById("payment-charges-section");
    if (!section) return {load() {}};
    const canSettle = section.dataset.canSettle === "1";
    const openBody = document.getElementById("payment-charges-open");
    const settledBody = document.getElementById("payment-charges-settled");
    let available = 0;

    async function settle(body) {
        try {
            await apiRequest(`${endpoint}settle-charges/`, {method: "POST", body});
            globalMessage("سود و جریمه با این دریافت تسویه شد.", true);
            await onChanged?.();
        } catch (error) {
            showError(error);
        }
    }

    function actionButton(label, onClick, className = "btn btn-sm btn-light-primary") {
        const button = document.createElement("button");
        button.type = "button";
        button.className = className;
        button.textContent = label;
        button.addEventListener("click", onClick);
        return button;
    }

    function render(data) {
        const open = data.open || [];
        const settled = data.settlements || [];
        document.getElementById("payment-charges-empty").hidden = open.length > 0 || settled.length > 0;
        document.getElementById("payment-charges-open-wrap").hidden = !open.length;
        document.getElementById("payment-charges-settle-all-bar").hidden = !(canSettle && open.length && available > 0);
        openBody.replaceChildren(...open.map((charge) => {
            const row = document.createElement("tr");
            const link = document.createElement("a");
            link.href = `/invoices/${charge.invoice}/`;
            link.textContent = charge.invoice_number;
            link.dir = "ltr";
            const cell = document.createElement("td");
            cell.append(link);
            row.append(cell);
            appendCell(row, persian(charge.installment_label));
            appendCell(row, charge.kind_display);
            appendCell(row, displayDay(charge.due_date));
            appendMoneyCell(row, charge.open_amount);
            const actions = document.createElement("td");
            if (canSettle && available > 0) {
                actions.append(actionButton("تسویه", () => settle({charges: [{charge: charge.id}]})));
            }
            row.append(actions);
            return row;
        }));
        document.getElementById("payment-charges-settled-wrap").hidden = !settled.length;
        settledBody.replaceChildren(...settled.map((item) => {
            const row = document.createElement("tr");
            appendCell(row, item.invoice_number);
            appendCell(row, persian(item.installment_label));
            appendCell(row, item.kind_display);
            appendMoneyCell(row, item.amount);
            const status = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = `badge badge-light-${item.is_reversed ? "secondary" : "success"}`;
            badge.textContent = item.is_reversed ? "آزاد شده" : "فعال";
            status.append(badge);
            row.append(status);
            const actions = document.createElement("td");
            if (canSettle && !item.is_reversed) {
                actions.append(actionButton("آزاد کردن", async () => {
                    if (!(await confirmDialog(`تسویهٔ ${money(item.amount)} آزاد شود؟ این مبلغ دوباره بدهی مشتری و ماندهٔ این دریافت می‌شود.`))) return;
                    try {
                        await apiRequest(`${endpoint}release-charge-settlement/`, {method: "POST", body: {settlement: item.id}});
                        globalMessage("تسویه آزاد شد.", true);
                        await onChanged?.();
                    } catch (error) {
                        showError(error);
                    }
                }, "btn btn-sm btn-light"));
            }
            row.append(actions);
            return row;
        }));
    }

    document.getElementById("payment-charges-settle-all")?.addEventListener("click", () => settle({}));

    return {
        /** Draw for this receipt; a non-receipt, unconfirmed or customer-less one shows nothing. */
        async load(payment) {
            const usable = payment && payment.direction === "receipt" && payment.status === "confirmed" && payment.customer;
            section.hidden = !usable;
            if (!usable) return;
            available = Number(payment.unallocated_amount || 0);
            try {
                render(await apiRequest(`${endpoint}charges/`));
            } catch (error) {
                showError(error);
            }
        },
    };
}
