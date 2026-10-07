import {campaignLabel} from "dolphin/core/labels.js";
import {apiRequest} from "dolphin/core/api.js";
import {apiDateTime} from "dolphin/core/jalali.js";
import {clearMessages, formPayload, showError, withSubmit} from "dolphin/core/messages.js";
import {loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
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
            ["کمپین", selectedOptionText(document.getElementById("create-lead-campaign"))],
            ["مسئول", selectedOptionText(document.getElementById("create-lead-assignee"))],
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
        // A new lead belongs to a campaign (2.40.0).
        const campaigns = await loadAllPages("/api/v1/campaigns/?ordering=name");
        const select = document.getElementById("create-lead-campaign");
        campaigns.filter((campaign) => campaign.status !== "archived" && !campaign.children_count)
            .forEach((campaign) => select.append(new Option(
                campaignLabel(campaign), String(campaign.id),
            )));
        // «مسئول» offers only the chosen campaign's responsibles — its own, or
        // its parent's when it names none (2.40.35, product owner: «دراپ‌داون
        // مسئول باید فقط مسئولان آن کمپین را نشان دهد»); `create_lead` refuses
        // anyone else. The names are the ones this reader may assign to
        // (`lead_assignee_choices`: everyone who works leads for a manager,
        // only «خودم» for a marketer).
        const byId = new Map(campaigns.map((campaign) => [String(campaign.id), campaign]));
        const assignee = document.getElementById("create-lead-assignee");
        let assignable = [];
        try {
            assignable = JSON.parse(document.getElementById("create-lead-assignee-choices").textContent);
        } catch (error) {
            assignable = [];
        }
        const showResponsibles = () => {
            const campaign = byId.get(select.value);
            const parent = campaign?.parent ? byId.get(String(campaign.parent)) : null;
            const own = campaign?.responsibles || [];
            const ids = new Set((own.length ? own : (parent?.responsibles || [])).map(String));
            assignee.replaceChildren(assignee.options[0] || new Option("خودکار — تقسیم برابر بین مسئولان کمپین", ""));
            assignable.filter(([pk]) => ids.has(String(pk)))
                .forEach(([pk, name]) => assignee.append(new Option(name, String(pk))));
            assignee.value = "";
        };
        select.addEventListener("change", showResponsibles);
        document.getElementById("open-create-lead").addEventListener("click", showResponsibles);
    } catch (error) { showError(error); }
    createForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(createForm, async () => {
            const data = new FormData(createForm);
            // No customer and no interested product: a campaign is worked
            // from its target audience.
            const payload = formPayload(createForm, ["source", "status", "notes"]);
            payload.campaign = Number(data.get("campaign"));
            if (data.get("assign_to")) payload.assign_to = Number(data.get("assign_to"));
            if (data.get("next_follow_up_at")) payload.next_follow_up_at = apiDateTime(data.get("next_follow_up_at"));
            const lead = await apiRequest(createForm.action, {method: "POST", body: payload});
            window.location.assign(`/leads/${lead.id}/`);
        });
    });
}
