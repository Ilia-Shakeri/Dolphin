import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {globalMessage, showError} from "dolphin/core/messages.js";

/**
 * The internal AI assistant on a customer's profile (2.40.55, feature
 * `ai_assistant`): a case summary, a next action, or an SMS draft the
 * reader may copy. It only suggests; every rule is `assistant.services`.
 */
export function setupProfileAssistant(customerId) {
    const card = document.getElementById("profile-assistant");
    if (!card) return;
    const loading = document.getElementById("profile-assistant-loading");
    const result = document.getElementById("profile-assistant-result");
    const errorSlot = card.querySelector('[data-error-for="assistant"]');
    const buttons = [...card.querySelectorAll("[data-assistant-kind]")];

    async function ask(kind) {
        buttons.forEach((button) => { button.disabled = true; });
        errorSlot.textContent = "";
        result.hidden = true;
        loading.hidden = false;
        try {
            const body = {kind, customer: Number(customerId)};
            if (kind === "sms_draft") body.instruction = document.getElementById("profile-assistant-goal").value.trim();
            const answer = await apiRequest("/api/v1/assistant/suggest/", {method: "POST", body});
            document.getElementById("profile-assistant-title").textContent = answer.title;
            document.getElementById("profile-assistant-text").textContent = answer.text;
            document.getElementById("profile-assistant-meta").textContent =
                `پیشنهاد هوش مصنوعی، ${displayDate(answer.generated_at)}، در ${toPersianDigits(String(answer.seconds))} ثانیه — پیش از استفاده بازبینی کنید.`;
            result.hidden = false;
        } catch (error) {
            showError(error, card);
        } finally {
            loading.hidden = true;
            buttons.forEach((button) => { button.disabled = false; });
        }
    }

    buttons.forEach((button) => button.addEventListener("click", () => ask(button.dataset.assistantKind)));
    document.getElementById("profile-assistant-copy").addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(document.getElementById("profile-assistant-text").textContent);
            globalMessage("متن کپی شد.", true);
        } catch {
            globalMessage("کپی انجام نشد؛ متن را دستی انتخاب کنید.");
        }
    });
}
