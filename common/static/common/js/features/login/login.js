import {apiRequest} from "dolphin/core/api.js";
import {formPayload, withSubmit} from "dolphin/core/messages.js";

export function setupLogin() {
    const form = document.getElementById("login-form");
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            await apiRequest(form.action, {method: "POST", body: formPayload(form, ["username", "password"])});
            window.location.assign("/");
        });
    });
}
