import {ApiError, STATUS_MESSAGES} from "dolphin/core/api.js";
import {reportWizardErrors, wizardsByForm} from "dolphin/core/form-errors.js";

export function globalMessage(message, success = false) {
    const node = document.getElementById("global-message");
    if (!node) return;
    node.textContent = message;
    // The markup ships hard-coded `alert-danger` — right for the far more
    // common error case, wrong for a success message with no matching CSS
    // of its own. `alert-success` is the theme's own real class (`style.
    // bundle.rtl.css` styles it already); this swaps the two rather than
    // toggling a bare `.success` modifier that nothing in the stylesheet
    // has ever answered, which is why every past success message here —
    // "کاربر ذخیره شد" and the rest — still painted the danger red.
    node.classList.toggle("alert-success", success);
    node.classList.toggle("alert-danger", !success);
    node.hidden = false;
    node.focus?.();
}

export function clearMessages(form) {
    document.getElementById("global-message")?.setAttribute("hidden", "");
    form?.querySelectorAll("[data-error-for]").forEach((node) => { node.textContent = ""; });
    // A wizard's review-step summary is built from those same slots, so it
    // is stale the moment they are emptied (`reportWizardErrors` below).
    if (form) wizardsByForm.get(form)?.summary.clear();
}

export function errorText(error) {
    if (!(error instanceof ApiError)) return "ارتباط با سامانه برقرار نشد. دوباره تلاش کنید.";
    return STATUS_MESSAGES[error.status] || "خطایی رخ داد. دوباره تلاش کنید.";
}

/**
 * Turn one field's error payload into a sentence a reader can act on.
 *
 * DRF nests. A plain field gives `["..."]`, but a nested serializer used
 * with `many=True` — the split-allocation form is one — gives a list of
 * per-row objects like `[{invoice: ["..."]}]`. Joining that list directly
 * printed the literal text `[object Object]` where the reason should be,
 * which told the operator nothing and looked like a crash.
 *
 * Walking the structure instead means any shape DRF produces comes out as
 * readable text, and a shape nobody anticipated degrades to its own values
 * rather than to a stringified object.
 */
function flattenErrorValue(value) {
    if (value === null || value === undefined) return "";
    if (Array.isArray(value)) {
        return value.map(flattenErrorValue).filter(Boolean).join(" ");
    }
    if (typeof value === "object") {
        return Object.values(value).map(flattenErrorValue).filter(Boolean).join(" ");
    }
    return String(value);
}

export function showError(error, form = null) {
    if (error instanceof ApiError && error.payload?.error?.code === "authentication_failed") {
        window.location.assign("/login/");
        return;
    }
    let hasFieldError = false;
    if (form && error instanceof ApiError && error.payload && typeof error.payload === "object") {
        form.querySelectorAll("[data-error-for]").forEach((node) => {
            const value = error.payload[node.dataset.errorFor];
            if (value !== undefined) {
                node.textContent = flattenErrorValue(value);
                hasFieldError = true;
            }
        });
        // Inside a wizard those slots are on steps the reader cannot see
        // from the review step they just submitted from, so the same
        // reasons are also summarised where they *are* standing.
        if (hasFieldError) reportWizardErrors(form);
    }
    globalMessage(hasFieldError && error.status === 400 ? STATUS_MESSAGES[400] : errorText(error));
}

export function formPayload(form, names) {
    const data = new FormData(form);
    return Object.fromEntries(names.map((name) => [name, String(data.get(name) || "")]));
}

export async function withSubmit(form, task) {
    clearMessages(form);
    const button = form.querySelector("button[type='submit']");
    button.disabled = true;
    try { await task(); } catch (error) { showError(error, form); } finally { button.disabled = false; }
}
