import {apiRequest} from "dolphin/core/api.js";
import {displayDate} from "dolphin/core/jalali.js";
import {globalMessage, showError, withSubmit} from "dolphin/core/messages.js";

/**
 * `/settings/sms-provider/` — this deployment's own outbound SMS gateway
 * (`communications.models.SmsProviderSettings`). Same load/submit shape
 * as `setupBrandingSettings` above, with two things that function does
 * not need: an auth-mode-dependent section (the OAuth2 fields are
 * useless, and hidden, in `api_key` mode) and a "تست اتصال" button that
 * calls a second endpoint against whatever is already saved.
 */
export function setupSmsProviderSettings() {
    const form = document.getElementById("sms-provider-form");
    if (!form) return;
    const loading = document.getElementById("sms-provider-loading");
    const authModeField = document.getElementById("sms-provider-auth-mode");
    const oauthSection = document.getElementById("sms-provider-oauth-section");
    const oauthHeading = document.getElementById("sms-provider-oauth-heading");
    const passwordField = document.getElementById("sms-provider-token-password");
    const passwordNote = document.getElementById("sms-provider-token-password-note");
    const updatedNote = document.getElementById("sms-provider-updated-note");
    const testButton = document.getElementById("sms-provider-test-button");
    const testResult = document.getElementById("sms-provider-test-result");

    function syncOAuthVisibility() {
        const isOAuth = authModeField.value === "oauth2_password";
        oauthSection.hidden = !isOAuth;
        oauthHeading.hidden = !isOAuth;
    }
    authModeField.addEventListener("change", syncOAuthVisibility);

    function fillUpdatedNote(data) {
        if (!data.updated_by_name) { updatedNote.textContent = ""; return; }
        updatedNote.textContent = `آخرین به‌روزرسانی: ${data.updated_by_name} — ${displayDate(data.updated_at)}`;
    }

    function fill(data) {
        document.getElementById("sms-provider-enabled").checked = Boolean(data.is_enabled);
        document.getElementById("sms-provider-label").value = data.label || "";
        authModeField.value = data.auth_mode;
        document.getElementById("sms-provider-number-style").value = data.recipient_number_style;
        document.getElementById("sms-provider-send-url").value = data.send_url || "";
        document.getElementById("sms-provider-sender-id").value = data.sender_id || "";
        document.getElementById("sms-provider-timeout").value = data.timeout_seconds;
        document.getElementById("sms-provider-body-template").value = data.body_template || "";
        document.getElementById("sms-provider-headers").value = data.headers || "";
        document.getElementById("sms-provider-token-url").value = data.token_url || "";
        document.getElementById("sms-provider-token-username").value = data.token_username || "";
        document.getElementById("sms-provider-token-extra").value = data.token_extra_params || "";
        document.getElementById("sms-provider-test-url").value = data.test_url || "";
        passwordField.value = "";
        passwordNote.textContent = data.has_token_password
            ? "رمزی از قبل ذخیره شده — برای تغییر، مقدار تازه وارد کنید؛ برای نگه‌داشتن مقدار فعلی، خالی بگذارید."
            : "هنوز رمزی ذخیره نشده.";
        fillUpdatedNote(data);
        syncOAuthVisibility();
    }

    async function load() {
        try {
            const data = await apiRequest("/api/v1/sms-provider-settings/");
            fill(data);
            loading.classList.add("d-none");
            form.classList.remove("d-none");
        } catch (error) {
            showError(error);
            loading.classList.add("d-none");
        }
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const payload = {
                is_enabled: document.getElementById("sms-provider-enabled").checked,
                label: document.getElementById("sms-provider-label").value,
                auth_mode: authModeField.value,
                recipient_number_style: document.getElementById("sms-provider-number-style").value,
                send_url: document.getElementById("sms-provider-send-url").value,
                sender_id: document.getElementById("sms-provider-sender-id").value,
                timeout_seconds: Number(document.getElementById("sms-provider-timeout").value || 10),
                body_template: document.getElementById("sms-provider-body-template").value,
                headers: document.getElementById("sms-provider-headers").value,
                token_url: document.getElementById("sms-provider-token-url").value,
                token_username: document.getElementById("sms-provider-token-username").value,
                token_extra_params: document.getElementById("sms-provider-token-extra").value,
                test_url: document.getElementById("sms-provider-test-url").value,
            };
            // Omitted, not sent blank: leaving the password field empty
            // means "keep the value already stored" — sending an empty
            // string would instead clear it (see the update service's
            // own "independent and optional" contract).
            if (passwordField.value) payload.token_password = passwordField.value;
            const data = await apiRequest("/api/v1/sms-provider-settings/", {method: "POST", body: payload});
            fill(data);
            globalMessage("تنظیمات سامانهٔ پیامک ذخیره شد.", true);
        });
    });

    testButton?.addEventListener("click", async () => {
        testButton.disabled = true;
        testResult.hidden = true;
        try {
            const data = await apiRequest("/api/v1/sms-provider-settings/test/", {method: "POST", body: {}});
            testResult.hidden = false;
            testResult.className = `alert d-flex align-items-center p-4 mt-3 ${data.success ? "alert-success" : "alert-danger"}`;
            testResult.textContent = data.status_detail;
        } catch (error) {
            showError(error);
        } finally {
            testButton.disabled = false;
        }
    });

    load();
}
