import {apiRequest} from "dolphin/core/api.js";
import {showError} from "dolphin/core/messages.js";

/**
 * Internal chat: a slide-in drawer, matching the purchased theme's own
 * `dolphin_drawer_chat` pattern (header icon, `data-dolphin-drawer`, the same
 * message-bubble classes) with two states inside it — a thread list, or
 * one open conversation — since the theme's own demo shows a single
 * fixed conversation and this panel has many.
 *
 * No websocket in this codebase (no channel-layer infrastructure exists
 * anywhere else here), so "live" means polling — the same choice the
 * agent work queue and every report already make. What makes this feel
 * live rather than merely refreshed: both intervals run only while the
 * drawer is actually open (checked against the theme's own `drawer-on`
 * class on every tick, the same class the drawer gets however it was
 * opened — the header icon, or the theme's own overlay/Escape handling),
 * and opening the drawer polls immediately rather than waiting for the
 * next tick. A closed drawer costs nothing; an open one updates every
 * few seconds without anyone touching it.
 */
/**
 * PRELIMINARY, UNCOMMITTED — see integration/apps.py. Mints a fresh
 * short-lived hand-off token per click (never once per page load, so a
 * tab left open never tries to use an expired one) and follows it
 * straight to Dolphin Accounting, already signed in.
 */
export function setupGoToAccounting() {
    const button = document.getElementById("go-to-accounting");
    if (!button) return;
    button.addEventListener("click", async (event) => {
        event.preventDefault();
        button.classList.add("disabled");
        try {
            const data = await apiRequest("/api/v1/integration/handoff/mint/", {method: "POST"});
            window.location.assign(data.url);
        } catch (error) {
            showError(error);
        } finally {
            button.classList.remove("disabled");
        }
    });
}
