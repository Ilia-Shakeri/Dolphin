import {apiRequest} from "dolphin/core/api.js";
import {ROLE_LABELS} from "dolphin/core/config.js";
import {displayDate} from "dolphin/core/jalali.js";
import {clearMessages, formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {clearChatCache} from "dolphin/shell/chat.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {appendCell} from "dolphin/ui/table.js";

/**
 * The signed-in user's own sessions, opened from the header user menu.
 *
 * Every row is identified by the opaque reference the server sends; the
 * session key never reaches the browser, so nothing here could be replayed
 * as a credential even if the page were captured. The user's current
 * session is marked and cannot be ended from this dialog — signing yourself
 * out of the page you are using is never what "end this session" means.
 */
export function setupSessionsDialog() {
    const dialog = document.getElementById("sessions-dialog");
    const open = document.getElementById("open-sessions");
    if (!dialog || !open) return;
    const body = document.getElementById("sessions-table-body");
    const wrap = document.getElementById("sessions-table-wrap");
    const loading = document.getElementById("sessions-loading");
    const empty = document.getElementById("sessions-empty");
    const revokeOthers = document.getElementById("revoke-other-sessions");
    const close = document.getElementById("close-sessions");

    async function load() {
        loading.hidden = false;
        wrap.hidden = true;
        empty.hidden = true;
        try {
            const data = await apiRequest("/api/v1/auth/me/sessions/");
            const others = data.results.filter((item) => !item.is_current);
            body.replaceChildren(...data.results.map((item) => {
                const row = document.createElement("tr");
                appendCell(row, describeDevice(item.user_agent));
                appendCell(row, item.ip_address || "—").dir = "ltr";
                appendCell(row, item.started_at ? displayDate(item.started_at) : "—");
                appendCell(row, displayDate(item.expires_at));
                const actions = document.createElement("td");
                if (item.is_current) {
                    const badge = document.createElement("span");
                    badge.className = "badge badge-light-success";
                    badge.textContent = "نشست فعلی";
                    actions.append(badge);
                } else {
                    const button = document.createElement("button");
                    button.className = "btn btn-sm btn-light-danger";
                    button.type = "button";
                    button.textContent = "پایان";
                    button.addEventListener("click", () => revoke(item.reference, button));
                    actions.append(button);
                }
                row.append(actions);
                return row;
            }));
            loading.hidden = true;
            empty.hidden = data.results.length > 0;
            wrap.hidden = data.results.length === 0;
            revokeOthers.disabled = others.length === 0;
        } catch (error) {
            loading.hidden = true;
            showError(error);
        }
    }

    async function revoke(reference, button) {
        button.disabled = true;
        clearMessages();
        try {
            await apiRequest("/api/v1/auth/me/sessions/", {method: "POST", body: {reference}});
            globalMessage("نشست پایان یافت.", true);
            await load();
        } catch (error) {
            button.disabled = false;
            showError(error);
        }
    }

    revokeOthers.addEventListener("click", async () => {
        if (!await confirmDialog("همه نشست‌های دیگر شما پایان یابد؟")) return;
        revokeOthers.disabled = true;
        clearMessages();
        try {
            const result = await apiRequest("/api/v1/auth/me/sessions/", {method: "POST", body: {}});
            globalMessage(`${result.ended} نشست پایان یافت.`, true);
            await load();
        } catch (error) {
            revokeOthers.disabled = false;
            showError(error);
        }
    });

    open.addEventListener("click", () => {
        dialog.showModal();
        load();
    });
    close.addEventListener("click", () => dialog.close());
}

/**
 * A user agent string reduced to something a person recognises.
 *
 * Deliberately coarse: the point is "is this me on my own machine", not
 * device fingerprinting, and a full user agent string on screen tells the
 * reader nothing they can act on.
 */
function describeDevice(userAgent) {
    const text = String(userAgent || "");
    if (!text) return "—";
    const platform =
        /Windows/i.test(text) ? "ویندوز"
        : /Android/i.test(text) ? "اندروید"
        : /(iPhone|iPad|iOS)/i.test(text) ? "iOS"
        : /Mac OS X/i.test(text) ? "مک"
        : /Linux/i.test(text) ? "لینوکس"
        : "نامشخص";
    const browser =
        /Edg\//i.test(text) ? "Edge"
        : /OPR\//i.test(text) ? "Opera"
        : /Chrome\//i.test(text) ? "Chrome"
        : /Firefox\//i.test(text) ? "Firefox"
        : /Safari\//i.test(text) ? "Safari"
        : "مرورگر";
    return `${browser} — ${platform}`;
}

export function setupLogout() {
    const form = document.getElementById("logout-form");
    if (!form) return;
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            await apiRequest(form.action, {method: "POST"});
            // The chat drawer's copy of this account's conversations
            // must not outlive the session in this tab (2.18.5).
            clearChatCache();
            window.location.assign("/login/");
        });
    });
}

export async function setupProfile() {
    const form = document.getElementById("profile-form");
    const loading = document.getElementById("profile-loading");
    try {
        const user = await apiRequest("/api/v1/auth/me/");
        document.getElementById("profile-username").value = user.username;
        document.getElementById("profile-role").value = ROLE_LABELS[user.role];
        ["first_name", "last_name", "email", "phone"].forEach((name) => {
            document.getElementById(`profile-${name.replaceAll("_", "-")}`).value = user[name] || "";
        });
        loading.hidden = true;
        form.hidden = false;
    } catch (error) {
        loading.hidden = true;
        showError(error);
        return;
    }
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            await apiRequest(form.action, {method: "PATCH", body: formPayload(form, ["first_name", "last_name", "email", "phone"])});
            globalMessage("پروفایل ذخیره شد.", true);
        });
    });
}
