import {apiRequest} from "dolphin/core/api.js";
import {clearMessages, showError} from "dolphin/core/messages.js";
import {registerPopover} from "dolphin/ui/popover.js";

/**
 * `/settings/` — this reader's own panel preferences.
 *
 * Replaces `setupDashboardLayoutSettings`, retired in 2.8.0 along with
 * the deployment-wide `/settings/dashboard/` page it drove; the
 * arrangement it used to edit is now edited on the dashboard itself
 * (`setupDashboardEditor`).
 *
 * The form is rendered server-side with the saved values already
 * selected, so there is no loading state and no first paint showing the
 * defaults before the real choice arrives. What this adds on top is the
 * save, and the two previews that have to happen without a reload:
 * the colour theme (which `DolphinThemeMode` also keeps in `localStorage`)
 * and the typeface/scale, so the reader can see the choice they are
 * about to keep.
 */
/**
 * Tabs switch without a reload. Every pane is already in the page; the links
 * keep their `?tab=` href so each tab stays linkable and works without script.
 */
function setupSettingsTabs() {
    const tabs = Array.from(document.querySelectorAll("[data-settings-tab]"));
    if (!tabs.length) return;
    const show = (key) => {
        tabs.forEach((tab) => {
            const active = tab.dataset.settingsTab === key;
            tab.classList.toggle("active", active);
            tab.setAttribute("aria-selected", String(active));
        });
        document.querySelectorAll("[data-settings-pane]").forEach((pane) => {
            pane.hidden = pane.dataset.settingsPane !== key;
        });
    };
    tabs.forEach((tab) => tab.addEventListener("click", (event) => {
        event.preventDefault();
        show(tab.dataset.settingsTab);
        history.replaceState(null, "", tab.getAttribute("href"));
    }));
}

export function setupSettingsPage() {
    setupSettingsTabs();
    const form = document.getElementById("preferences-form");
    if (!form) return;
    const saved = document.getElementById("preferences-saved");

    //: Each typeface choice carries its own CSS stack
    //: (`data-font-stack`, rendered from `PANEL_FONT_FAMILIES`), so the
    //: live preview reads the server's mapping rather than keeping a copy
    //: of it here (until 2.18.7 it did, and the two could drift). What is
    //: applied on every other page is still the `<style>` element the
    //: server renders; this is only the preview of it.
    //: Absolute pixels off the theme's own 13px base, not percentages
    //: of the browser default — see `PANEL_FONT_SCALES` for why.
    const FONT_SIZES = {sm: "12px", md: "13px", lg: "15px"};
    const DEFAULT_FONT_STACK = "IRANSansWeb, Helvetica, sans-serif";

    function preview() {
        const scale = form.elements.font_scale?.value;
        const chosen = form.querySelector("input[name='font_family']:checked");
        const stack = (chosen && chosen.dataset.fontStack) || DEFAULT_FONT_STACK;
        const size = FONT_SIZES[scale] || FONT_SIZES.md;
        // `setProperty` with the priority argument, because the two
        // declarations this has to beat are the theme's own
        // `html, body { font-size: 13px !important }` and its literal
        // `html, body { font-family: ... }` — an inline style without
        // `important` loses to the first of those. Same rules the server
        // emits in `common.preferences.preference_css`; this is only the
        // live preview of them.
        [document.documentElement, document.body].forEach((node) => {
            node.style.setProperty("font-family", stack);
            node.style.setProperty("font-size", size, "important");
        });
        document.documentElement.style.setProperty("--bs-font-sans-serif", stack);
    }

    function previewTheme(choice) {
        const resolved = choice === "system"
            ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
            : choice;
        document.documentElement.setAttribute("data-bs-theme", resolved);
        try {
            // The same key `DolphinThemeMode` and the header's own theme
            // switcher use, so the two never disagree about what this
            // machine last showed. The server-side preference is still
            // what decides on a *different* machine; see the head
            // script in base.html for which of the two wins.
            localStorage.setItem("data-bs-theme-mode", choice);
        } catch (error) {
            // Private mode can refuse localStorage. The preference is
            // saved server-side regardless, which is the copy that
            // matters; only this machine's pre-paint shortcut is lost.
        }
    }

    // «قلم پنل» is a dropdown since 2.23.2: the theme's own menu, opened
    // under its toggle, and closed again once a face is chosen.
    const fontToggle = document.getElementById("preference-font-family-toggle");
    const fontMenu = registerPopover({
        toggle: fontToggle,
        panel: document.getElementById("preference-font-family"),
        onOpen: () => form.querySelector("input[name='font_family']:checked")?.focus(),
    });

    form.addEventListener("change", (event) => {
        if (saved) saved.hidden = true;
        if (event.target?.name === "font_family" && fontToggle) {
            const current = fontToggle.querySelector("[data-font-family-current]");
            if (current) {
                current.textContent = event.target.dataset.fontLabel || "";
                current.style.fontFamily = event.target.dataset.fontStack || "";
            }
            fontMenu?.close();
            fontToggle.focus();
        }
        const name = event.target?.name;
        // The three size glyphs are the theme's option cards; the card
        // around the checked radio carries `.active` (2.18.6), the same
        // class the server renders on the saved one.
        if (name === "font_scale" || name === "font_family") {
            const cards = name === "font_scale" ? ".font-scale-option" : ".font-family-option";
            form.querySelectorAll(cards).forEach((card) => {
                card.classList.toggle("active", card.contains(event.target));
            });
        }
        if (name === "font_family" || name === "font_scale") preview();
        if (name === "theme") previewTheme(event.target.value);
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearMessages(form);
        const data = new FormData(form);
        try {
            await apiRequest("/api/v1/preferences/", {
                method: "POST",
                body: {
                    font_family: data.get("font_family"),
                    font_scale: data.get("font_scale"),
                    currency_unit: data.get("currency_unit"),
                    theme: data.get("theme"),
                },
            });
        } catch (error) {
            showError(error, form);
            return;
        }
        if (saved) saved.hidden = false;
        // Reloaded rather than only previewed: the currency unit reaches
        // the panel script through a `<body>` attribute read once at
        // load (`CURRENCY_UNIT`), and every amount already on screen
        // elsewhere in the panel was formatted with the old one. A
        // preference that visibly takes effect only after the next
        // navigation is the kind of half-applied setting a reader
        // reasonably reads as broken.
        window.location.reload();
    });
}
