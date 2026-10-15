import {apiRequest} from "dolphin/core/api.js";
import {globalMessage, showError, withSubmit} from "dolphin/core/messages.js";

/**
 * Settings → «اقساط» (2.40.51): this company's instalment rules, one card per
 * advanced instalment feature the deployment runs. GET fills the form and a
 * PATCH sends what it holds; every rule is `billing.installment_settings`.
 */
const NUMBERS = ["remind_days_before", "remind_days_after", "remind_send_hour"];
const TEXTS = ["template_before", "template_due", "template_overdue"];

export function setupInstallmentsSection() {
    const form = document.getElementById("installment-settings-form");
    if (!form) return;
    const loading = document.getElementById("installment-settings-loading");
    const field = (name) => document.getElementById(`installment-${name.replaceAll("_", "-")}`);

    function fill(data) {
        for (const name of NUMBERS) {
            if (field(name)) field(name).value = String(data[name]);
        }
        for (const name of TEXTS) {
            if (field(name)) field(name).value = data[name];
        }
        if (field("remind_on_due")) field("remind_on_due").checked = Boolean(data.remind_on_due);
        const missing = document.getElementById("installment-sms-provider-missing");
        if (missing) missing.hidden = Boolean(data.sms_provider_ready);
        const tokens = document.getElementById("installment-template-tokens");
        if (tokens) tokens.textContent = data.tokens.join("، ");
    }

    apiRequest("/api/v1/installment-settings/")
        .then((data) => {
            fill(data);
            loading.hidden = true;
            form.hidden = false;
        })
        .catch((error) => {
            loading.textContent = "تنظیمات اقساط دریافت نشد.";
            showError(error);
        });

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!field("remind_on_due")) return;
        withSubmit(form, async () => {
            const body = {remind_on_due: field("remind_on_due").checked};
            for (const name of NUMBERS) body[name] = Number(field(name).value);
            for (const name of TEXTS) body[name] = field(name).value;
            fill(await apiRequest("/api/v1/installment-settings/", {method: "PATCH", body}));
            globalMessage("تنظیمات اقساط ذخیره شد.", true);
        });
    });
}
