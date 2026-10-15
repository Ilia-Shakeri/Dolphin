import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDay} from "dolphin/core/jalali.js";
import {globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money, moneyToStorage} from "dolphin/core/money.js";
import {syncSegmented} from "dolphin/ui/segmented.js";

/**
 * Settings → «اقساط» (2.40.51): this company's instalment rules, one card per
 * advanced instalment feature the deployment runs. GET fills the form and a
 * PATCH sends what it holds; every rule is `billing.installment_settings`.
 */
const NUMBERS = ["remind_days_before", "remind_days_after", "remind_send_hour", "late_fee_grace_days"];
const CHOICES = ["interest_method", "late_fee_mode"];
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
        // Interest and late fees (2.40.52).
        for (const name of CHOICES) {
            if (!field(name)) continue;
            field(name).value = data[name];
            syncSegmented(document.querySelector(`[data-segmented-for="${field(name).id}"]`));
        }
        if (field("interest_default_rate")) field("interest_default_rate").value = String(Number(data.interest_default_rate));
        if (field("late_fee_value")) {
            field("late_fee_value").value = data.late_fee_mode === "fixed"
                ? money(data.late_fee_value, {withCurrency: false})
                : String(Number(data.late_fee_value));
            labelFeeValue();
        }
        if (field("late_fee_cap")) field("late_fee_cap").value = money(data.late_fee_cap, {withCurrency: false});
        const since = document.getElementById("installment-late-fee-since");
        if (since) {
            since.hidden = !data.late_fee_since;
            since.textContent = data.late_fee_since
                ? `جریمه فقط برای قسط‌هایی است که از ${displayDay(data.late_fee_since)} به بعد سررسید شده‌اند؛ قسط‌های پیش از آن هرگز جریمه نمی‌گیرند.`
                : "";
        }
        const missing = document.getElementById("installment-sms-provider-missing");
        if (missing) missing.hidden = Boolean(data.sms_provider_ready);
        const tokens = document.getElementById("installment-template-tokens");
        if (tokens) tokens.textContent = data.tokens.join("، ");
    }

    function labelFeeValue() {
        const label = document.getElementById("installment-late-fee-value-label");
        if (label) label.textContent = field("late_fee_mode")?.value === "fixed" ? "مبلغ جریمه (ریال)" : "درصد جریمه از ماندهٔ قسط";
    }
    field("late_fee_mode")?.addEventListener("change", labelFeeValue);

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
        withSubmit(form, async () => {
            const body = {};
            if (field("remind_on_due")) body.remind_on_due = field("remind_on_due").checked;
            for (const name of NUMBERS) if (field(name)) body[name] = Number(field(name).value);
            for (const name of TEXTS) if (field(name)) body[name] = field(name).value;
            for (const name of CHOICES) if (field(name)) body[name] = field(name).value;
            if (field("interest_default_rate")) body.interest_default_rate = field("interest_default_rate").value.trim() || "0";
            if (field("late_fee_value")) {
                body.late_fee_value = field("late_fee_mode").value === "fixed"
                    ? (moneyToStorage(field("late_fee_value").value) || "0")
                    : (field("late_fee_value").value.trim() || "0");
            }
            if (field("late_fee_cap")) body.late_fee_cap = moneyToStorage(field("late_fee_cap").value) || "0";
            fill(await apiRequest("/api/v1/installment-settings/", {method: "PATCH", body}));
            globalMessage("تنظیمات اقساط ذخیره شد.", true);
        });
    });
}
