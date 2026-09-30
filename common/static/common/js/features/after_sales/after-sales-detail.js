import {apiRequest} from "dolphin/core/api.js";
import {apiDateTime, displayDate} from "dolphin/core/jalali.js";
import {formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {fillSelect, loadAllPages} from "dolphin/ui/lists.js";
import {appendCell} from "dolphin/ui/table.js";

function fillAfterSales(item) {
    document.getElementById("after-sales-subject-detail").value = item.subject;
    document.getElementById("after-sales-customer-detail").value = item.customer_name || item.customer;
    document.getElementById("after-sales-sale-detail").value = item.sale || "—";
    document.getElementById("after-sales-document-detail").value = item.document || "—";
    document.getElementById("after-sales-status-detail").value = item.status;
    document.getElementById("after-sales-assigned-detail").value = item.assigned_to_display || "تخصیص‌نیافته";
    document.getElementById("after-sales-created-by-detail").value = item.created_by_display || item.created_by;
    document.getElementById("after-sales-closed-detail").value = displayDate(item.closed_at);
    document.getElementById("after-sales-appointment-detail").value = item.next_appointment_at ? displayDate(item.next_appointment_at) : "زمان‌بندی‌نشده";
    document.getElementById("after-sales-description-detail").value = item.description;
    document.getElementById("after-sales-actions").hidden = Boolean(item.closed_at);
}

async function loadAfterSalesHistory(id) {
    const rows = await loadAllPages(`/api/v1/after-sales/${id}/history/`);
    const eventLabels = {created: "ایجاد", assigned: "تخصیص", status_changed: "تغییر وضعیت", closed: "بستن", appointment_scheduled: "زمان‌بندی قرار"};
    const nodes = rows.map((item) => {
        const row = document.createElement("tr");
        const fromTo = item.event === "appointment_scheduled"
            ? (item.appointment_at ? displayDate(item.appointment_at) : "لغو قرار")
            : `${item.from_status || "—"} / ${item.to_status || "—"}`;
        [eventLabels[item.event] || item.event, fromTo, `${item.from_user_display || "—"} / ${item.to_user_display || "—"}`, item.actor_display, item.reason || "—", displayDate(item.created_at)].forEach((value) => appendCell(row, value));
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
    try { [item] = await Promise.all([apiRequest(endpoint), loadAfterSalesHistory(id)]); fillAfterSales(item); document.getElementById("after-sales-detail-loading").hidden = true; document.getElementById("after-sales-detail-content").hidden = false; } catch (error) { document.getElementById("after-sales-detail-loading").hidden = true; showError(error); return; }
    const statusForm = document.getElementById("after-sales-status-form");
    statusForm.addEventListener("submit", (event) => { event.preventDefault(); withSubmit(statusForm, async () => { item = await apiRequest(statusForm.action, {method: "POST", body: formPayload(statusForm, ["to_status", "reason"])}); fillAfterSales(item); statusForm.reset(); await loadAfterSalesHistory(id); globalMessage("وضعیت پرونده ثبت شد.", true); }); });
    const appointmentForm = document.getElementById("after-sales-appointment-form");
    appointmentForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(appointmentForm, async () => {
            const raw = new FormData(appointmentForm).get("appointment_at");
            const body = {
                appointment_at: apiDateTime(String(raw || "")) || null,
                reason: String(new FormData(appointmentForm).get("reason") || ""),
            };
            item = await apiRequest(appointmentForm.action, {method: "POST", body});
            fillAfterSales(item);
            await loadAfterSalesHistory(id);
            globalMessage(body.appointment_at ? "قرار زمان‌بندی شد." : "قرار لغو شد.", true);
        });
    });
    const assignForm = document.getElementById("after-sales-assign-form");
    if (assignForm) {
        try { fillSelect(document.getElementById("after-sales-to-user"), await loadAllPages("/api/v1/after-sales/assignees/"), (user) => user.display, "مسئول را انتخاب کنید"); } catch (error) { showError(error); }
        assignForm.addEventListener("submit", (event) => { event.preventDefault(); withSubmit(assignForm, async () => { item = await apiRequest(assignForm.action, {method: "POST", body: formPayload(assignForm, ["to_user", "reason"])}); fillAfterSales(item); assignForm.reset(); await loadAfterSalesHistory(id); globalMessage("پرونده تخصیص یافت.", true); }); });
        document.getElementById("close-after-sales").addEventListener("click", async () => { if (!await confirmDialog("پرونده بسته شود؟ بازگشایی هنوز تصویب نشده.")) return; try { item = await apiRequest(`${endpoint}close/`, {method: "POST", body: {}}); fillAfterSales(item); await loadAfterSalesHistory(id); globalMessage("پرونده بسته شد.", true); } catch (error) { showError(error); } });
    }
}
