import {apiRequest} from "dolphin/core/api.js";
import {apiDateTime, displayDate} from "dolphin/core/jalali.js";
import {clearMessages, formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {afterSalesConfig, caseBadge, PRIORITY_TONES, stagesFor} from "dolphin/features/after_sales/after-sales.js";
import {fillSelect, loadAllPages} from "dolphin/ui/lists.js";
import {liveRecord} from "dolphin/ui/live-record.js";
import {appendCell} from "dolphin/ui/table.js";

const config = afterSalesConfig();

/** The case's open stages, for moving it on or reopening it (2.40.60). */
function fillStages(select, item, {keepCurrent = false} = {}) {
    select.replaceChildren(...stagesFor(config, item.case_type)
        .filter((stage) => stage.kind === "open" && stage.is_active && (keepCurrent || stage.key !== item.stage))
        .map((stage) => new Option(stage.label, stage.key)));
}

function deadlineRow(label, due, doneAt, closed) {
    const row = document.createElement("tr");
    appendCell(row, label);
    appendCell(row, due ? displayDate(due) : "بدون مهلت");
    appendCell(row, doneAt ? displayDate(doneAt) : "—");
    const state = document.createElement("td");
    if (!due) state.append(caseBadge("—", "secondary"));
    else if (doneAt) state.append(caseBadge(new Date(doneAt) <= new Date(due) ? "به‌موقع" : "با تأخیر", new Date(doneAt) <= new Date(due) ? "success" : "warning"));
    else if (closed) state.append(caseBadge("—", "secondary"));
    else state.append(caseBadge(new Date(due) < new Date() ? "گذشته از مهلت" : "در جریان", new Date(due) < new Date() ? "danger" : "primary"));
    row.append(state);
    return row;
}

function fillAfterSales(item) {
    document.getElementById("after-sales-subject-detail").value = item.subject;
    document.getElementById("after-sales-customer-detail").value = item.customer_name || item.customer;
    document.getElementById("after-sales-sale-detail").value = item.sale || "—";
    document.getElementById("after-sales-document-detail").value = item.document || "—";
    document.getElementById("after-sales-status-detail").value = item.stage_label || item.status;
    document.getElementById("after-sales-assigned-detail").value = item.assigned_to_display || "تخصیص‌نیافته";
    document.getElementById("after-sales-created-by-detail").value = item.created_by_display || item.created_by;
    document.getElementById("after-sales-appointment-detail").value = item.next_appointment_at ? displayDate(item.next_appointment_at, {gregorian: false}) : "زمان‌بندی‌نشده";
    document.getElementById("after-sales-description-detail").value = item.description;
    const badges = [caseBadge(item.case_type_label || "بدون نوع", "info"), caseBadge(`اولویت ${item.priority_label}`, PRIORITY_TONES[item.priority] || "secondary")];
    if (item.closed_at) badges.push(caseBadge(`بسته‌شده ${displayDate(item.closed_at)}${item.final_result_label ? ` — ${item.final_result_label}` : ""}`, "success"));
    if (item.overdue?.length) badges.push(caseBadge("گذشته از مهلت", "danger"));
    if (item.escalated_at && !item.closed_at) badges.push(caseBadge(`ارجاع به مدیر ${displayDate(item.escalated_at)}`, "warning"));
    document.getElementById("after-sales-badges").replaceChildren(...badges);
    const closed = Boolean(item.closed_at);
    const rows = [deadlineRow("پاسخ اولیه", item.response_due, item.responded_at, closed)];
    if (item.priority === "critical") rows.push(deadlineRow("برنامهٔ رسیدگی", item.plan_due, item.planned_at, closed));
    rows.push(deadlineRow("حل پرونده", item.resolution_due, item.closed_at, false));
    document.getElementById("after-sales-deadlines").replaceChildren(...rows);
    document.getElementById("after-sales-actions").hidden = closed;
    const reopenCard = document.getElementById("after-sales-reopen-card");
    if (reopenCard) reopenCard.hidden = !closed;
    fillStages(document.getElementById("after-sales-to-status"), item);
    document.getElementById("after-sales-plan-form").hidden = item.priority !== "critical" || Boolean(item.planned_at);
    const priority = document.getElementById("after-sales-priority-select");
    if (priority) priority.value = item.priority;
}

const EVENT_LABELS = {
    created: "ایجاد", assigned: "تخصیص", status_changed: "تغییر وضعیت", closed: "بستن", appointment_scheduled: "زمان‌بندی قرار",
    reopened: "بازگشایی", priority_changed: "تغییر اولویت", type_changed: "تغییر نوع", planned: "برنامهٔ رسیدگی",
    escalated: "ارجاع به مدیر", survey_sent: "پیامک نظرسنجی",
};

async function loadAfterSalesHistory(id) {
    const rows = await loadAllPages(`/api/v1/after-sales/${id}/history/`);
    const nodes = rows.map((item) => {
        const row = document.createElement("tr");
        const fromTo = item.event === "appointment_scheduled"
            ? (item.appointment_at ? displayDate(item.appointment_at) : "لغو قرار")
            : `${item.from_status || "—"} / ${item.to_status || "—"}`;
        [EVENT_LABELS[item.event] || item.event, fromTo, `${item.from_user_display || "—"} / ${item.to_user_display || "—"}`, item.actor_display, item.reason || "—", displayDate(item.created_at)].forEach((value) => appendCell(row, value));
        return row;
    });
    document.getElementById("after-sales-history-body").replaceChildren(...nodes);
    document.getElementById("after-sales-history-loading").hidden = true;
    document.getElementById("after-sales-history-empty").hidden = Boolean(nodes.length);
    document.getElementById("after-sales-history-wrap").hidden = !nodes.length;
}

export async function setupAfterSalesDetail() {
    const id = document.body.dataset.afterSalesId, endpoint = `/api/v1/after-sales/${id}/`;
    let item;
    // Live (2.40.41): the case and its history redraw in place when it changes elsewhere.
    const settle = liveRecord({read: () => apiRequest(endpoint), draw: async (value) => { item = value; fillAfterSales(value); await loadAfterSalesHistory(id); }});
    try { [item] = await Promise.all([apiRequest(endpoint), loadAfterSalesHistory(id)]); fillAfterSales(item); settle(item); document.getElementById("after-sales-detail-loading").hidden = true; document.getElementById("after-sales-detail-content").hidden = false; } catch (error) { document.getElementById("after-sales-detail-loading").hidden = true; showError(error); return; }

    /** Send one form, redraw the case and its history, say so. */
    function action(form, message, body = () => formPayload(form, [...new FormData(form).keys()].filter((key) => key !== "csrfmiddlewaretoken")), after = () => {}) {
        form?.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                item = await apiRequest(form.action, {method: "POST", body: body()});
                fillAfterSales(item);
                settle(item);
                form.reset();
                after();
                await loadAfterSalesHistory(id);
                globalMessage(message, true);
            });
        });
    }

    action(document.getElementById("after-sales-status-form"), "مرحلهٔ پرونده ثبت شد.");
    action(document.getElementById("after-sales-plan-form"), "برنامهٔ رسیدگی ثبت شد.");
    action(document.getElementById("after-sales-priority-form"), "اولویت تغییر کرد و مهلت‌ها دوباره حساب شد.");
    const appointmentForm = document.getElementById("after-sales-appointment-form");
    action(appointmentForm, "قرار ثبت شد.", () => {
        const data = new FormData(appointmentForm);
        return {appointment_at: apiDateTime(String(data.get("appointment_at") || "")) || null, reason: String(data.get("reason") || "")};
    });
    const assignForm = document.getElementById("after-sales-assign-form");
    if (assignForm) {
        try { fillSelect(document.getElementById("after-sales-to-user"), await loadAllPages("/api/v1/after-sales/assignees/"), (user) => user.display, "مسئول را انتخاب کنید"); } catch (error) { showError(error); }
        action(assignForm, "پرونده تخصیص یافت.", () => formPayload(assignForm, ["to_user", "reason"]));
    }

    // Closing asks for the final result; reopening for a reason (2.40.60).
    const closeDialog = document.getElementById("close-after-sales-dialog");
    const closeForm = document.getElementById("close-after-sales-form");
    document.getElementById("close-after-sales")?.addEventListener("click", () => { closeForm.reset(); clearMessages(closeForm); closeDialog.showModal(); });
    action(closeForm, "پرونده بسته شد.", () => formPayload(closeForm, ["final_result", "reason"]), () => closeDialog.close());
    const reopenDialog = document.getElementById("reopen-after-sales-dialog");
    const reopenForm = document.getElementById("reopen-after-sales-form");
    document.getElementById("open-reopen-after-sales")?.addEventListener("click", () => {
        reopenForm.reset();
        clearMessages(reopenForm);
        fillStages(document.getElementById("reopen-after-sales-stage"), item, {keepCurrent: true});
        reopenDialog.showModal();
    });
    action(reopenForm, "پرونده بازگشایی شد.", () => formPayload(reopenForm, ["to_stage", "reason"]), () => reopenDialog.close());
    [closeDialog, reopenDialog].forEach((dialog) => dialog?.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close())));
}
