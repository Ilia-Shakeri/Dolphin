import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDate, displayDate, displayDay} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {appendCell, appendMoneyCell} from "dolphin/ui/table.js";

/**
 * Change or extend what is left of an instalment plan (2.40.51, feature
 * `installment_reschedule`) — the button, its dialog with a live preview from
 * the server, and the plan's history of changes. The rule and every check are
 * `billing.installments.reschedule_plan`; this only asks and shows.
 */
export function setupInstallmentReschedule({endpoint, onChanged}) {
    const bar = document.getElementById("invoice-installments-reschedule-bar");
    const dialog = document.getElementById("installments-reschedule-dialog");
    const historyBox = document.getElementById("invoice-installments-history");
    const historyList = document.getElementById("invoice-installments-history-list");
    let summary = null;

    function renderHistory(items) {
        if (!historyBox) return;
        historyBox.hidden = !items?.length;
        historyList.replaceChildren(...(items || []).map((item) => {
            const entry = document.createElement("li");
            entry.className = "border border-dashed border-gray-300 rounded p-4";
            const head = document.createElement("span");
            head.className = "d-block fw-semibold text-gray-900";
            head.textContent = `${displayDate(item.at)} — ${item.actor_display}`;
            const terms = document.createElement("span");
            terms.className = "d-block text-gray-700 fs-7 mt-1";
            terms.textContent = `${money(item.remaining_amount)} در ${toPersianDigits(String(item.installment_count))} قسط، از ${displayDay(item.first_due)} هر ${toPersianDigits(String(item.interval_days))} روز`;
            const reason = document.createElement("span");
            reason.className = "d-block text-gray-800 fs-7 mt-2";
            reason.textContent = `دلیل: ${item.reason}`;
            entry.append(head, terms, reason);
            return entry;
        }));
    }

    function openRows() {
        return (summary?.rows || []).filter((row) => Number(row.balance_due) > 0);
    }

    if (dialog && bar) {
        const form = document.getElementById("installments-reschedule-form");
        const count = document.getElementById("installments-reschedule-count");
        const firstDue = document.getElementById("installments-reschedule-first-due");
        const interval = document.getElementById("installments-reschedule-interval");
        const reason = document.getElementById("installments-reschedule-reason");
        const previewBox = document.getElementById("installments-reschedule-preview");
        const previewBody = document.getElementById("installments-reschedule-preview-body");
        let previewTimer = null;
        let previewToken = 0;

        function terms() {
            return {
                installment_count: Number(count.value),
                first_due: apiDate(firstDue.value),
                interval_days: Number(interval.value),
            };
        }

        async function preview() {
            const body = terms();
            if (!Number.isInteger(body.installment_count) || !body.first_due || !Number.isInteger(body.interval_days)) {
                previewBox.hidden = true;
                return;
            }
            const token = ++previewToken;
            try {
                const result = await apiRequest(`${endpoint}reschedule-installments/`, {method: "POST", body: {...body, preview: true}});
                if (token !== previewToken) return;
                clearMessages(form);
                previewBody.replaceChildren(...result.rows.map((row) => {
                    const line = document.createElement("tr");
                    appendCell(line, `قسط ${toPersianDigits(String(row.sequence))}`);
                    appendCell(line, displayDay(row.due_date));
                    appendMoneyCell(line, row.amount);
                    return line;
                }));
                previewBox.hidden = false;
            } catch (error) {
                if (token !== previewToken) return;
                previewBox.hidden = true;
                showError(error, form);
            }
        }

        function schedulePreview() {
            window.clearTimeout(previewTimer);
            previewTimer = window.setTimeout(preview, 300);
        }
        [count, firstDue, interval].forEach((field) => {
            field.addEventListener("input", schedulePreview);
            field.addEventListener("change", schedulePreview);
        });

        document.getElementById("invoice-installments-reschedule").addEventListener("click", () => {
            const rows = openRows();
            if (!rows.length) return;
            clearMessages(form);
            form.reset();
            const remaining = rows.reduce((sum, row) => sum + Number(row.balance_due), 0);
            document.getElementById("installments-reschedule-summary").textContent =
                `ماندهٔ ${money(remaining.toFixed(2))} در ${toPersianDigits(String(rows.length))} قسط پرداخت‌نشده، در برنامهٔ تازه تقسیم می‌شود.`;
            count.value = String(rows.length);
            const firstOpen = rows.find((row) => row.due_date)?.due_date;
            firstDue.value = firstOpen ? displayDay(firstOpen, {gregorian: false}) : "";
            interval.value = String(summary.interval_days_current || 30);
            previewBox.hidden = true;
            dialog.showModal();
            schedulePreview();
        });

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const updated = await apiRequest(`${endpoint}reschedule-installments/`, {
                    method: "POST", body: {...terms(), reason: reason.value.trim()},
                });
                dialog.close();
                globalMessage("برنامهٔ تازهٔ اقساط ثبت شد.", true);
                onChanged?.(updated);
            });
        });
    }

    return {
        update(next) {
            summary = next;
            if (bar) bar.hidden = !(next?.reschedulable && openRows().length);
            renderHistory(next?.reschedules);
        },
    };
}
