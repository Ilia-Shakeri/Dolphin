import {apiRequest} from "dolphin/core/api.js";
import {apiDateTime, localDateTimeValue} from "dolphin/core/jalali.js";
import {clearMessages, formPayload, showError, withSubmit} from "dolphin/core/messages.js";
import {loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {interactionRow} from "dolphin/ui/rows.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

export async function setupInteractions() {
    const form = document.getElementById("interaction-search-form");
    setupListFilter("interaction");
    const controller = setupPagedList({
        key: "interactions", form,
        search: document.getElementById("interaction-search"),
        endpoint(page) {
            const query = new URLSearchParams({page: String(page), ordering: document.getElementById("interaction-ordering").value});
            const search = document.getElementById("interaction-search").value.trim();
            if (search) query.set("search", search);
            const result = document.getElementById("interaction-result-filter").value;
            if (result) query.set("result", result);
            if (document.getElementById("interaction-qualified-filter").checked) query.set("qualified", "true");
            return `/api/v1/interactions/?${query}`;
        }, renderRow: interactionRow,
    });
    const dialog = document.getElementById("create-interaction-dialog");
    const createForm = document.getElementById("create-interaction-form");
    let memberOptions = [];
    // The outcome list (2.40.58): what each one asks for.
    let outcomes = [];
    try { outcomes = JSON.parse(document.getElementById("call-outcomes").textContent); } catch (error) { outcomes = []; }
    const resultSelect = document.getElementById("create-interaction-result");
    const qualifiedField = document.getElementById("create-interaction-qualified-field");
    const qualified = document.getElementById("create-interaction-qualified");
    const followUp = document.getElementById("create-interaction-follow-up");
    function syncOutcome() {
        const chosen = outcomes.find((item) => item.key === resultSelect.value);
        qualifiedField.hidden = !chosen?.may_qualify;
        if (qualifiedField.hidden) qualified.checked = false;
        followUp.required = Boolean(chosen?.needs_follow_up);
        followUp.closest("div").querySelector("label").classList.toggle("required", followUp.required);
        document.getElementById("create-interaction-dnc-note").hidden = !chosen?.stops_contact;
    }
    resultSelect.addEventListener("change", syncOutcome);
    function renderInteractionReview() {
        renderWizardReview(document.getElementById("create-interaction-review"), [
            ["مشتری", document.getElementById("create-interaction-member").value || "—"],
            ["شماره تماس", document.getElementById("create-interaction-phone").value],
            ["جهت", selectedOptionText(document.getElementById("create-interaction-direction"))],
            ["نتیجهٔ تماس", selectedOptionText(resultSelect) + (qualified.checked ? " — واجد شرایط" : "")],
            ["زمان تماس", document.getElementById("create-interaction-occurred").value],
            ["پیگیری بعدی", document.getElementById("create-interaction-follow-up").value || "—"],
            ["یادداشت", document.getElementById("create-interaction-notes").value || "—"],
        ]);
    }
    const interactionWizard = setupWizard(dialog, {onReachLastStep: renderInteractionReview});
    document.getElementById("open-create-interaction").addEventListener("click", () => {
        createForm.reset();
        clearMessages(createForm);
        syncOutcome();
        document.getElementById("create-interaction-occurred").value = localDateTimeValue(new Date().toISOString());
        interactionWizard?.goFirst();
        dialog.showModal();
    });
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    try {
        await controller.load();
        // The identities this caller may call. The endpoint is already
        // scoped to their own campaigns, so a marketer searches only the
        // people on campaigns assigned to them — no client-side filtering
        // decides that.
        memberOptions = await loadAllPages("/api/v1/target-audience/?ordering=full_name");
        const list = document.getElementById("target-member-options");
        list.replaceChildren(...memberOptions.map((item) => {
            const option = document.createElement("option");
            // The label is what the user types against and what is matched
            // back to an id on submit.
            option.value = `${item.full_name} — ${item.raw_phone}`;
            return option;
        }));
    } catch (error) { showError(error); }

    /** The identity whose label the user typed, or null. */
    function chosenMember(typed) {
        const text = String(typed || "").trim();
        if (!text) return null;
        return memberOptions.find(
            (item) => `${item.full_name} — ${item.raw_phone}` === text
        ) || memberOptions.find((item) => item.full_name === text) || null;
    }

    createForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(createForm, async () => {
            const data = new FormData(createForm);
            const member = chosenMember(data.get("target_member"));
            if (member === null) {
                const slot = createForm.querySelector('[data-error-for="target_member"]');
                if (slot) slot.textContent = "یکی از هویت‌های جامعه هدف را انتخاب کنید.";
                return;
            }
            const payload = formPayload(createForm, ["phone", "direction", "result", "notes"]);
            payload.qualified = qualified.checked;
            // The campaign comes from the identity, so the two can never
            // disagree about which campaign the call belongs to.
            payload.lead = member.lead;
            payload.target_member = member.id;
            payload.occurred_at = apiDateTime(data.get("occurred_at"));
            if (data.get("next_follow_up_at")) payload.next_follow_up_at = apiDateTime(data.get("next_follow_up_at"));
            const interaction = await apiRequest(createForm.action, {method: "POST", body: payload});
            window.location.assign(`/interactions/${interaction.id}/`);
        });
    });
}
