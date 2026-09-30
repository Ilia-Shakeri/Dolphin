import {apiRequest} from "dolphin/core/api.js";
import {globalMessage, withSubmit} from "dolphin/core/messages.js";

/**
 * Settings → «امتیازدهی اشخاص» (2.20.0): one form per person type. Only
 * rendered for a Platform Admin where scoring runs; the endpoint checks
 * both again.
 */
export function setupScoringSection() {
    document.querySelectorAll("[data-scoring-form]").forEach((form) => {
        form.querySelector("[data-scoring-defaults]")?.addEventListener("click", () => {
            form.querySelectorAll("input[data-default]").forEach((input) => { input.value = input.dataset.default; });
        });
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const weights = {};
                form.querySelectorAll("input[name]").forEach((input) => { weights[input.name] = Number(input.value); });
                await apiRequest("/api/v1/scoring-settings/", {
                    method: "PUT",
                    body: {person_type: form.dataset.scoringForm, weights},
                });
                globalMessage("وزن‌های امتیازدهی ذخیره شد. امتیازها در محاسبهٔ بعدی با وزن تازه حساب می‌شوند.", true);
            });
        });
    });
}
