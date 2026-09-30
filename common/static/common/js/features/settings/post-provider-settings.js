import {apiRequest} from "dolphin/core/api.js";
import {displayDate} from "dolphin/core/jalali.js";
import {globalMessage, showError, withSubmit} from "dolphin/core/messages.js";

/**
 * The post-carrier API connection settings page — the same shape as
 * `setupSmsProviderSettings` just above, simplified to the one auth
 * form (a static header key) `sales/postal_provider.py` supports.
 * Product owner, 2026-09-21: «تنظیمات سامانه پست هم مثل پیامک باید
 * صفحه برای تنظیم کردن api داشته باشه».
 */
export function setupPostProviderSettings() {
    const form = document.getElementById("post-provider-form");
    if (!form) return;
    const loading = document.getElementById("post-provider-loading");
    const keyField = document.getElementById("post-provider-key");
    const keyNote = document.getElementById("post-provider-key-note");
    const updatedNote = document.getElementById("post-provider-updated-note");
    const testButton = document.getElementById("post-provider-test-button");
    const testResult = document.getElementById("post-provider-test-result");

    function fillUpdatedNote(data) {
        if (!data.updated_by_name) { updatedNote.textContent = ""; return; }
        updatedNote.textContent = `آخرین به‌روزرسانی: ${data.updated_by_name} — ${displayDate(data.updated_at)}`;
    }

    function fill(data) {
        document.getElementById("post-provider-enabled").checked = Boolean(data.is_enabled);
        document.getElementById("post-provider-label").value = data.label || "";
        document.getElementById("post-provider-base-url").value = data.base_url || "";
        document.getElementById("post-provider-key-header").value = data.api_key_header || "";
        document.getElementById("post-provider-account").value = data.sender_account_code || "";
        document.getElementById("post-provider-timeout").value = data.timeout_seconds;
        document.getElementById("post-provider-test-url").value = data.test_url || "";
        keyField.value = "";
        keyNote.textContent = data.has_api_key
            ? "کلیدی از قبل ذخیره شده — برای تغییر، مقدار تازه وارد کنید؛ برای نگه‌داشتن مقدار فعلی، خالی بگذارید."
            : "هنوز کلیدی ذخیره نشده.";
        fillUpdatedNote(data);
    }

    async function load() {
        try {
            const data = await apiRequest("/api/v1/post-provider-settings/");
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
                is_enabled: document.getElementById("post-provider-enabled").checked,
                label: document.getElementById("post-provider-label").value,
                base_url: document.getElementById("post-provider-base-url").value,
                api_key_header: document.getElementById("post-provider-key-header").value,
                sender_account_code: document.getElementById("post-provider-account").value,
                timeout_seconds: Number(document.getElementById("post-provider-timeout").value || 10),
                test_url: document.getElementById("post-provider-test-url").value,
            };
            // Omitted, not sent blank: leaving the key field empty means
            // "keep the value already stored" — the same contract
            // `setupSmsProviderSettings` follows for `token_password`.
            if (keyField.value) payload.api_key = keyField.value;
            const data = await apiRequest("/api/v1/post-provider-settings/", {method: "POST", body: payload});
            fill(data);
            globalMessage("تنظیمات سامانهٔ پست ذخیره شد.", true);
        });
    });

    testButton?.addEventListener("click", async () => {
        testButton.disabled = true;
        testResult.hidden = true;
        try {
            const data = await apiRequest("/api/v1/post-provider-settings/test/", {method: "POST", body: {}});
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
