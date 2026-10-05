import {apiRequest} from "dolphin/core/api.js";
import {formPayload, withSubmit} from "dolphin/core/messages.js";

const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)");

/**
 * The sign-in form (2.40.4). The request is exactly what it was — the same
 * two fields to the same endpoint, then the panel — with the feedback a
 * sign-in page owes its reader around it: the button says it is working,
 * a refusal shakes the card once and is announced (`#global-message` is
 * `role="alert"`), Caps Lock is pointed out, the password can be shown, and
 * a success fades the card before the panel opens.
 */
export function setupLogin() {
    const form = document.getElementById("login-form");
    const card = document.getElementById("login-card");
    const submit = form.querySelector("button[type='submit']");
    setupPasswordToggle();
    setupCapsLockHint();

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        submit.setAttribute("aria-busy", "true");
        let signedIn = false;
        withSubmit(form, async () => {
            await apiRequest(form.action, {method: "POST", body: formPayload(form, ["username", "password"])});
            signedIn = true;
        }).finally(() => {
            if (signedIn) {
                // Leave the button busy: the panel is on its way.
                card.classList.add("login-success");
                window.setTimeout(() => window.location.assign("/"), REDUCED_MOTION.matches ? 0 : 220);
                return;
            }
            submit.removeAttribute("aria-busy");
            shakeOnce(card);
        });
    });
}

/** One shake per refusal, restarted cleanly if the next one comes fast. */
function shakeOnce(card) {
    if (!card || REDUCED_MOTION.matches) return;
    card.classList.remove("login-shake");
    void card.offsetWidth;
    card.classList.add("login-shake");
    card.addEventListener("animationend", () => card.classList.remove("login-shake"), {once: true});
}

function setupPasswordToggle() {
    const input = document.getElementById("login-password");
    const toggle = document.getElementById("login-password-toggle");
    if (!input || !toggle) return;
    const icon = toggle.querySelector("i");
    toggle.addEventListener("click", () => {
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        toggle.setAttribute("aria-pressed", String(show));
        toggle.setAttribute("aria-label", show ? "پنهان کردن گذرواژه" : "نمایش گذرواژه");
        // di-eye draws from three paths, di-eye-slash from four.
        icon.className = `di-duotone ${show ? "di-eye-slash" : "di-eye"} fs-2`;
        icon.replaceChildren(...Array.from({length: show ? 4 : 3}, (_, index) => {
            const path = document.createElement("span");
            path.className = `path${index + 1}`;
            return path;
        }));
        // The caret stays where it was; the reader keeps typing.
        input.focus();
    });
}

function setupCapsLockHint() {
    const input = document.getElementById("login-password");
    const hint = document.getElementById("login-caps");
    if (!input || !hint) return;
    const update = (event) => {
        if (typeof event.getModifierState !== "function") return;
        hint.hidden = !event.getModifierState("CapsLock");
    };
    input.addEventListener("keydown", update);
    input.addEventListener("keyup", update);
    input.addEventListener("blur", () => { hint.hidden = true; });
}
