import {apiRequest} from "dolphin/core/api.js";
import {apiDateTime} from "dolphin/core/jalali.js";
import {clearMessages, formPayload, showError, withSubmit} from "dolphin/core/messages.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {leadRow} from "dolphin/ui/rows.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

export async function setupLeads() {
    const form = document.getElementById("lead-search-form");
    setupListFilter("lead");
    const controller = setupPagedList({
        key: "leads", form,
        search: document.getElementById("lead-search"),
        endpoint(page) {
            const query = new URLSearchParams({page: String(page), ordering: document.getElementById("lead-ordering").value});
            const search = document.getElementById("lead-search").value.trim();
            const status = document.getElementById("lead-status-filter").value.trim();
            if (search) query.set("search", search);
            if (status) query.set("status", status);
            return `/api/v1/leads/?${query}`;
        }, renderRow: leadRow,
    });
    const dialog = document.getElementById("create-lead-dialog");
    const createForm = document.getElementById("create-lead-form");
    function renderLeadReview() {
        renderWizardReview(document.getElementById("create-lead-review"), [
            ["منبع", document.getElementById("create-lead-source").value || "—"],
            ["کمپین یا نوبت", document.getElementById("create-lead-campaign").value || "—"],
            ["وضعیت", selectedOptionText(document.getElementById("create-lead-status"))],
            ["پیگیری بعدی", document.getElementById("create-lead-follow-up").value || "—"],
            ["یادداشت", document.getElementById("create-lead-notes").value || "—"],
        ]);
    }
    const leadWizard = setupWizard(dialog, {onReachLastStep: renderLeadReview});
    document.getElementById("open-create-lead").addEventListener("click", () => {
        createForm.reset();
        clearMessages(createForm);
        leadWizard?.goFirst();
        dialog.showModal();
    });
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    try {
        await controller.load();
    } catch (error) { showError(error); }
    createForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(createForm, async () => {
            const data = new FormData(createForm);
            // No customer and no interested product: a campaign is worked
            // from its target audience.
            const payload = formPayload(createForm, ["source", "campaign_or_batch", "status", "notes"]);
            if (data.get("next_follow_up_at")) payload.next_follow_up_at = apiDateTime(data.get("next_follow_up_at"));
            const lead = await apiRequest(createForm.action, {method: "POST", body: payload});
            window.location.assign(`/leads/${lead.id}/`);
        });
    });
}
