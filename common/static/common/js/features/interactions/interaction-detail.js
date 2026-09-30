import {apiRequest} from "dolphin/core/api.js";
import {displayDate} from "dolphin/core/jalali.js";
import {showError} from "dolphin/core/messages.js";
import {directionText} from "dolphin/ui/table.js";

export async function setupInteractionDetail() {
    const interactionId = document.body.dataset.interactionId;
    const loading = document.getElementById("interaction-detail-loading");
    const content = document.getElementById("interaction-detail-content");
    try {
        const interaction = await apiRequest(`/api/v1/interactions/${interactionId}/`);
        document.getElementById("interaction-lead").value = interaction.lead;
        document.getElementById("interaction-customer").value = interaction.customer_name || interaction.customer;
        document.getElementById("interaction-agent").value = interaction.agent_display || interaction.agent;
        document.getElementById("interaction-phone").value = interaction.phone;
        document.getElementById("interaction-direction").value = directionText(interaction.direction);
        document.getElementById("interaction-outcome").value = interaction.outcome;
        document.getElementById("interaction-occurred").value = displayDate(interaction.occurred_at);
        document.getElementById("interaction-follow-up").value = displayDate(interaction.next_follow_up_at);
        document.getElementById("interaction-notes").value = interaction.notes || "";
        loading.hidden = true; content.hidden = false;
    } catch (error) { loading.hidden = true; showError(error); }
}
