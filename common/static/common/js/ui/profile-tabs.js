import {showError} from "dolphin/core/messages.js";
import {motionBehavior} from "dolphin/core/motion.js";

// --- Person profile (2.19.0) ------------------------------------------
//
// One page for customers and users (`profiles/templates/profiles/
// profile.html`). The server renders the header and every tab's empty
// shell — only the tabs this reader may see — and this script fills a
// tab's data the first time that tab opens, so a profile with eight tabs
// costs one round of requests, not eight.

/**
 * The tab strip: WAI-ARIA tabs over the theme's `nav-line-tabs`, deep
 * linked through `?tab=` so a copied link opens the same tab and Back
 * returns to the previous one.
 *
 * `loaders[key]` runs once, the first time `key` opens; a failure is
 * shown in the page's own message area and leaves the other tabs alone.
 */
export function setupProfileTabs(loaders) {
    const tabs = Array.from(document.querySelectorAll("[data-profile-tab]"));
    if (!tabs.length) return null;
    const keys = tabs.map((tab) => tab.dataset.profileTab);
    const panes = new Map(
        Array.from(document.querySelectorAll("[data-profile-pane]")).map((pane) => [pane.dataset.profilePane, pane]),
    );
    const started = new Map();
    let current = null;

    function run(key) {
        if (!started.has(key)) {
            const loader = loaders[key];
            started.set(key, loader
                ? Promise.resolve().then(loader).catch((error) => showError(error))
                : Promise.resolve());
        }
        return started.get(key);
    }

    /** A missing-field link of the completion bar lands on the input itself. */
    function focusField(id) {
        const field = id && document.getElementById(id);
        if (!field) return;
        field.scrollIntoView({block: "center", behavior: motionBehavior()});
        field.focus({preventScroll: true});
    }

    function activate(key, {push = false, focus = false} = {}) {
        if (!panes.has(key)) key = keys[0];
        if (key === current) return run(key);
        current = key;
        tabs.forEach((tab) => {
            const on = tab.dataset.profileTab === key;
            tab.classList.toggle("active", on);
            tab.setAttribute("aria-selected", String(on));
            tab.tabIndex = on ? 0 : -1;
            if (on && focus) tab.focus();
        });
        panes.forEach((pane, paneKey) => { pane.hidden = paneKey !== key; });
        if (push) {
            const url = new URL(window.location.href);
            url.searchParams.set("tab", key);
            window.history.pushState({profileTab: key}, "", url);
        }
        return run(key);
    }

    tabs.forEach((tab, index) => {
        tab.addEventListener("click", (event) => {
            event.preventDefault();
            activate(tab.dataset.profileTab, {push: true});
        });
        // Arrow keys walk the strip. The page is RTL, so the next tab
        // is to the left.
        tab.addEventListener("keydown", (event) => {
            const rtl = document.documentElement.dir !== "ltr";
            const moves = {
                ArrowLeft: rtl ? 1 : -1,
                ArrowRight: rtl ? -1 : 1,
            };
            let target = null;
            if (event.key in moves) target = (index + moves[event.key] + tabs.length) % tabs.length;
            else if (event.key === "Home") target = 0;
            else if (event.key === "End") target = tabs.length - 1;
            if (target === null) return;
            event.preventDefault();
            activate(tabs[target].dataset.profileTab, {push: true, focus: true});
        });
    });

    // Every other way into a tab on this page: a quick action, «ویرایش»
    // on the overview, «همهٔ رویدادها», an entry under «بیشتر».
    document.addEventListener("click", (event) => {
        const link = event.target.closest("[data-profile-tab-link]");
        if (!link) return;
        event.preventDefault();
        const ready = activate(link.dataset.profileTabLink, {push: true});
        if (link.dataset.focus) {
            Promise.resolve(ready).then(() => focusField(link.dataset.focus));
        } else {
            document.getElementById(`profile-tab-${link.dataset.profileTabLink}`)
                ?.scrollIntoView({block: "nearest", behavior: motionBehavior()});
        }
    });

    window.addEventListener("popstate", () => {
        activate(new URLSearchParams(window.location.search).get("tab") || keys[0]);
    });

    activate(document.body.dataset.activeTab || keys[0]);
    return {activate};
}
