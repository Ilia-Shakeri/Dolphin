import {apiRequest} from "dolphin/core/api.js";
import {globalMessage, showError, withSubmit} from "dolphin/core/messages.js";

/**
 * `/branding/` — this deployment's own name/logo, Platform Admin only.
 *
 * Same shape as the attachments panel above: GET to fill the form, a
 * plain multipart POST (never JSON — `raw: true`) so the optional file
 * input rides along unencoded, and a re-fetch of the logo preview after
 * a successful save so the page reflects exactly what the server now
 * holds rather than assuming the upload matched what was picked.
 */
export function setupBrandingSettings() {
    const form = document.getElementById("branding-form");
    if (!form) return;
    const loading = document.getElementById("branding-loading");
    const nameField = document.getElementById("branding-display-name");
    const preview = document.getElementById("branding-logo-preview");
    const emptyNote = document.getElementById("branding-logo-empty");
    const removeRow = document.getElementById("branding-remove-logo-row");
    const removeBox = document.getElementById("branding-remove-logo");
    const DEFAULT_ACCENT_COLOR = "#1b84ff";
    const colorField = document.getElementById("branding-accent-color");
    const colorHexField = document.getElementById("branding-accent-color-hex");
    const colorResetButton = document.getElementById("branding-accent-color-reset");

    // The two accent-colour inputs — a native colour picker (always a
    // valid hex, no validation needed) and a plain text field for typing
    // one directly — stay mirrors of each other; each edit updates the
    // other rather than the two silently disagreeing about what will be
    // submitted.
    colorField.addEventListener("input", () => {
        colorHexField.value = colorField.value;
    });
    colorHexField.addEventListener("input", () => {
        if (/^#[0-9a-fA-F]{6}$/.test(colorHexField.value)) colorField.value = colorHexField.value;
    });
    colorResetButton.addEventListener("click", () => {
        colorField.value = DEFAULT_ACCENT_COLOR;
        colorHexField.value = "";
    });

    function showLogo(hasLogo) {
        if (hasLogo) {
            preview.src = `/api/v1/branding/logo/?v=${Date.now()}`;
            preview.classList.remove("d-none");
            emptyNote.classList.add("d-none");
        } else {
            preview.classList.add("d-none");
            preview.removeAttribute("src");
            emptyNote.classList.remove("d-none");
        }
        removeRow.hidden = !hasLogo;
        removeBox.checked = false;
    }

    async function load() {
        try {
            const data = await apiRequest("/api/v1/branding/");
            nameField.value = data.display_name || "";
            colorField.value = data.accent_color || DEFAULT_ACCENT_COLOR;
            colorHexField.value = data.accent_color || "";
            showLogo(Boolean(data.has_logo));
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
            const payload = new FormData();
            payload.set("display_name", nameField.value);
            payload.set("accent_color", colorHexField.value.trim());
            const file = document.getElementById("branding-logo-file").files[0];
            if (file) payload.set("logo", file);
            if (removeBox.checked) payload.set("remove_logo", "true");
            const data = await apiRequest("/api/v1/branding/", {method: "POST", body: payload, raw: true});
            document.getElementById("branding-logo-file").value = "";
            colorField.value = data.accent_color || DEFAULT_ACCENT_COLOR;
            colorHexField.value = data.accent_color || "";
            showLogo(Boolean(data.has_logo));
            globalMessage("تنظیمات برند ذخیره شد. برای دیدن رنگ تازه در همهٔ عناصر، صفحه را تازه کنید.", true);
        });
    });

    load();
}
