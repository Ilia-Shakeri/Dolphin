import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDay} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, withSubmit} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {appendCell, appendMoneyCell} from "dolphin/ui/table.js";

/**
 * Interest and late fees on an instalment invoice (2.40.52): the charges
 * table under the rows, the waiver dialog for a late fee, and the interest a
 * draft will carry. Every rule is `billing.installment_charges`.
 */
const STATUS_ACCENT = Object.freeze({open: "warning", paid: "success", waived: "secondary", cancelled: "secondary", moved: "info"});

/** `{sequence: amount}` of each row's interest, from a draft's preview or an
 * issued plan's charges (a charge moved by a reschedule is not counted). */
export function interestBySequence(summary) {
    if (summary?.interest_preview?.rows) {
        return Object.fromEntries(Object.entries(summary.interest_preview.rows).map(([sequence, amount]) => [Number(sequence), Number(amount)]));
    }
    const found = {};
    for (const charge of summary?.charges || []) {
        if (charge.kind !== "interest" || charge.status === "moved") continue;
        found[charge.installment_sequence] = (found[charge.installment_sequence] || 0) + Number(charge.amount);
    }
    return found;
}

export function setupInstallmentCharges({endpoint, onChanged}) {
    const box = document.getElementById("invoice-installment-charges");
    const body = document.getElementById("invoice-installment-charges-body");
    const canWaive = box?.dataset.canWaive === "1";
    const dialog = document.getElementById("installment-charge-waive-dialog");
    const note = document.getElementById("invoice-installments-interest-note");
    let waiving = null;

    if (dialog) {
        const form = document.getElementById("installment-charge-waive-form");
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const updated = await apiRequest(`${endpoint}waive-charge/`, {
                    method: "POST", body: {charge: waiving.id, reason: document.getElementById("installment-charge-waive-reason").value.trim()},
                });
                dialog.close();
                globalMessage("جریمه بخشیده شد.", true);
                onChanged?.(updated);
            });
        });
    }

    function openWaiver(charge) {
        waiving = charge;
        const form = document.getElementById("installment-charge-waive-form");
        clearMessages(form);
        form.reset();
        document.getElementById("installment-charge-waive-summary").textContent =
            `${money(charge.open_amount)} از جریمهٔ دیرکرد ${charge.installment_label.replace(/\d+/g, (digits) => toPersianDigits(digits))} بخشیده و در حساب مشتری بستانکار می‌شود.`;
        dialog.showModal();
    }

    function renderNote(summary) {
        if (!note) return;
        const preview = summary?.interest_preview;
        if (preview && Number(preview.total) > 0) {
            const rate = toPersianDigits(String(Number(preview.rate)));
            note.textContent = `با نرخ سالانهٔ ${rate} درصد به روش ${preview.method_display}، سود این اقساط ${money(preview.total)} می‌شود. هنگام صدور، جدا از فاکتور در حساب مشتری ثبت می‌شود.`;
            note.hidden = false;
        } else {
            note.hidden = true;
        }
    }

    return {
        update(summary) {
            renderNote(summary);
            const charges = summary?.charges || [];
            if (!box) return;
            box.hidden = !charges.length;
            body.replaceChildren(...charges.map((charge) => {
                const row = document.createElement("tr");
                appendCell(row, charge.kind_display);
                appendCell(row, charge.installment_label.replace(/\d+/g, (digits) => toPersianDigits(digits)));
                appendCell(row, displayDay(charge.due_date));
                appendMoneyCell(row, charge.amount);
                appendMoneyCell(row, charge.paid_amount);
                appendMoneyCell(row, charge.open_amount);
                const status = document.createElement("td");
                const badge = document.createElement("span");
                badge.className = `badge badge-light-${STATUS_ACCENT[charge.status] || "secondary"}`;
                badge.textContent = charge.status_display;
                status.append(badge);
                if (charge.release_reason) {
                    const reason = document.createElement("span");
                    reason.className = "d-block text-gray-700 fs-8 mt-1";
                    reason.textContent = charge.release_reason;
                    status.append(reason);
                }
                row.append(status);
                const actions = document.createElement("td");
                if (canWaive && dialog && charge.kind === "late_fee" && charge.status === "open" && Number(charge.open_amount) > 0) {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = "btn btn-sm btn-light";
                    button.textContent = "بخشیدن";
                    button.addEventListener("click", () => openWaiver(charge));
                    actions.append(button);
                }
                row.append(actions);
                return row;
            }));
        },
    };
}
