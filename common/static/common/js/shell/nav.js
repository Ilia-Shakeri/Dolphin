import {apiRequest} from "dolphin/core/api.js";
import {motionBehavior} from "dolphin/core/motion.js";
import {chartRedraws} from "dolphin/ui/charts.js";
import {registerPopover} from "dolphin/ui/popover.js";

/**
 * Keep `aria-expanded` truthful on the sidebar toggle.
 *
 * Opening and closing the sidebar itself is the theme's drawer
 * (`data-dolphin-drawer-toggle="#nav-toggle"`); this only mirrors that state
 * into the attribute a screen reader reads, which the drawer does not set.
 */
export function setupNav() {
    const toggle = document.getElementById("nav-toggle");
    const sidebar = document.getElementById("app-sidebar");
    if (!toggle || !sidebar) return;
    const sync = () => toggle.setAttribute("aria-expanded", String(sidebar.classList.contains("drawer-on")));
    new MutationObserver(sync).observe(sidebar, {attributes: true, attributeFilter: ["class"]});
    sync();
}

/**
 * Mark the sidebar entry the current page belongs to.
 *
 * The theme's own classes do the work: `.menu-link.active` colours the
 * entry, and `.here.show` on a parent `.menu-accordion` both opens it and
 * colours its title — so an entry inside a group lights up together with
 * its group, which is what the product asks for.
 *
 * Matching is by longest URL prefix rather than by an id per page, so a
 * detail route (`/customers/12/`) lights up the list entry it came from and
 * a page added later needs nothing here. Exactly one group is ever open:
 * the one containing the current page, or none on the dashboard.
 */
export function setupNavActiveState() {
    const sidebar = document.getElementById("app-sidebar");
    if (!sidebar) return;
    // Normally the current URL, but a page may name the entry it belongs to
    // instead. Receipts and disbursements are one document behind one detail
    // route, so `/payments/12/` prefix-matches «دریافت‌ها» whichever desk it
    // was opened from — and a disbursement lit the wrong entry. The page
    // knows its own direction server-side; this lets it say so.
    const path = document.body.dataset.navMatch || window.location.pathname;

    let best = null;
    let bestLength = -1;
    for (const link of sidebar.querySelectorAll(".menu-link[href]")) {
        const href = new URL(link.getAttribute("href"), window.location.origin).pathname;
        // "/" would otherwise prefix-match every page, so the dashboard
        // matches only itself.
        const matches = href === "/" ? path === "/" : path.startsWith(href);
        if (matches && href.length > bestLength) {
            best = link;
            bestLength = href.length;
        }
    }
    if (!best) return;

    for (const item of sidebar.querySelectorAll(".menu-item.menu-accordion")) {
        item.classList.remove("here", "show");
    }
    for (const link of sidebar.querySelectorAll(".menu-link.active")) {
        link.classList.remove("active");
    }

    best.classList.add("active");
    best.setAttribute("aria-current", "page");
    const group = best.closest(".menu-item.menu-accordion");
    if (group) {
        group.classList.add("here", "show");
    }
}

/**
 * Scroll a sidebar accordion group into view once it opens.
 *
 * `.menu-item.menu-accordion` groups (`base.html`) toggle open/closed
 * through the theme's own DolphinMenu (`data-dolphin-menu-trigger="click"`), which
 * animates `.show`/height but never scrolls the sidebar's own DolphinScroll
 * viewport (`#dolphin_app_sidebar_menu_scroll`) to follow it — so a group near
 * the bottom of a long menu (e.g. «مدیریت سامانه») opens its submenu
 * mostly or entirely below the fold, and reaching it means scrolling by
 * hand every time (product-owner request 2026-09-12).
 *
 * A fixed delay rather than a transitionend listener: DolphinMenu animates
 * height via its own timing, not a CSS transition this code can attach
 * to, and 300ms comfortably covers it without waiting on an event that
 * never fires.
 */
export function setupSidebarAccordionScroll() {
    const sidebar = document.getElementById("app-sidebar");
    const scroller = document.getElementById("dolphin_app_sidebar_menu_scroll");
    if (!sidebar || !scroller) return;

    sidebar.addEventListener("click", (event) => {
        const link = event.target.closest(".menu-item.menu-accordion > .menu-link");
        if (!link || !scroller.contains(link)) return;
        const group = link.closest(".menu-item.menu-accordion");
        window.setTimeout(() => {
            if (group.classList.contains("show")) {
                group.scrollIntoView({behavior: motionBehavior(), block: "nearest"});
            }
        }, 300);
    });
}

/**
 * Open and close the header user menu.
 *
 * The theme owns how the panel looks and its `.show` rule; DolphinMenu would
 * normally toggle that class and position the panel with Popper, which
 * lives in the plugins bundle this deployment does not load. Toggling the
 * class is the whole of what was missing — placement is two CSS lines in
 * dolphin.css — and `registerPopover` above is what does it now, for this
 * menu and for every other panel in the shell.
 */
export function setupUserMenu() {
    registerPopover({
        toggle: document.getElementById("user-menu-toggle"),
        panel: document.getElementById("user-menu"),
    });
}

/**
 * Stops a collapse from immediately undoing itself.
 *
 * The toggle sits on the sidebar's outer edge but is a child of it, so the
 * pointer that just clicked "collapse" is still inside the sidebar when the
 * collapse finishes — and hover-to-peek reopens it at once. The sidebar
 * never narrows, so the toggle never moves out from under the pointer
 * either. Confirmed in a real browser: the click flipped the attribute and
 * the width stayed at its full 265px until the pointer moved.
 *
 * The theme knows about this and holds the peek off for 300ms with an
 * `.animating` class, which is long enough for the animation and not for a
 * pointer that simply stays where it is.
 *
 * Suspending it by taking `data-dolphin-app-sidebar-hoverable` off the body,
 * rather than by adding a class of our own, is what keeps this to one line
 * of effect: every peek rule in the theme is keyed on that attribute, so
 * dropping it turns off the widened width and the expanded contents
 * together. A class fighting `:hover` would have suppressed the width and
 * left the wide brand and labels rendering inside a 75px box.
 *
 * Only when the pointer is genuinely over the sidebar: reaching the toggle
 * by keyboard leaves no pointer to wait for, and a suspension nothing would
 * ever clear would disable the peek for the rest of the page's life.
 */
export function setupSidebarPeekGuard() {
    const sidebar = document.getElementById("app-sidebar");
    const toggle = document.getElementById("dolphin_app_sidebar_toggle");
    if (!sidebar || !toggle) return;

    const HOVERABLE = "data-dolphin-app-sidebar-hoverable";
    toggle.addEventListener("click", () => {
        if (!sidebar.matches(":hover")) return;
        document.body.removeAttribute(HOVERABLE);
    });
    sidebar.addEventListener("mouseleave", () => {
        document.body.setAttribute(HOVERABLE, "true");
    });
}

/**
 * Redraw every chart when the panel changes theme.
 *
 * `DolphinThemeMode` writes `data-bs-theme` on `<html>`, and does it both when a
 * mode is picked and when a reader on "system" changes their OS setting, so
 * watching the attribute covers both without knowing which happened.
 */
export function setupChartThemeRedraw() {
    const root = document.documentElement;
    let previous = root.getAttribute("data-bs-theme");
    const observer = new MutationObserver(() => {
        const current = root.getAttribute("data-bs-theme");
        // The theme's own code touches this attribute on its way to the
        // same value; a redraw per touch would be a visible flicker.
        if (current === previous) return;
        previous = current;
        chartRedraws.forEach((redraw, chart) => {
            // A chart whose page has been replaced under it is gone; its
            // entry would otherwise keep the detached node alive.
            if (!chart.isConnected) {
                chartRedraws.delete(chart);
                return;
            }
            redraw();
        });
    });
    observer.observe(root, {attributes: true, attributeFilter: ["data-bs-theme"]});
}

export function setupThemeModePopup() {
    const item = document.querySelector("[data-theme-mode-item]");
    const trigger = document.getElementById("theme-mode-trigger");
    const popup = document.getElementById("theme-mode-popup");
    if (!item || !trigger || !popup) return;

    let hideTimer = null;

    function open() {
        window.clearTimeout(hideTimer);
        popup.hidden = false;
        trigger.setAttribute("aria-expanded", "true");
        // Which side has room is not knowable in advance: it depends on the
        // window width and where the user menu ended up. Measure once, and
        // flip only if the preferred side would put the popup off-screen.
        popup.classList.remove("is-flipped");
        const box = popup.getBoundingClientRect();
        if (box.left < 0 || box.right > window.innerWidth) {
            popup.classList.add("is-flipped");
        }
    }

    function close(delay = 0) {
        window.clearTimeout(hideTimer);
        hideTimer = window.setTimeout(() => {
            popup.hidden = true;
            trigger.setAttribute("aria-expanded", "false");
        }, delay);
    }

    item.addEventListener("mouseenter", open);
    item.addEventListener("mouseleave", () => close(180));
    trigger.addEventListener("click", (event) => {
        event.preventDefault();
        if (popup.hidden) open();
        else close();
    });

    // Choosing a mode closes the popup, updates the row, and saves the
    // choice. The switching itself is DolphinThemeMode's; this only reacts to
    // it.
    popup.querySelectorAll("[data-dolphin-element='mode']").forEach((button) => {
        // The row's own icon follows `data-bs-theme` through the theme's
        // CSS, so nothing here has to update it.
        button.addEventListener("click", () => {
            close(120);
            // Saved server-side as well as in `localStorage`, so this
            // switcher and the settings page («حالت رنگی», 2.8.0)
            // cannot disagree about what the reader chose — and so the
            // choice follows them to another browser. Without this the
            // settings page would silently win back on the next load,
            // and a reader who used the header switcher would watch
            // their theme revert.
            const mode = button.dataset.dolphinValue;
            if (!mode) return;
            apiRequest("/api/v1/preferences/", {method: "POST", body: {theme: mode}}).catch(() => {
                // The theme has already changed on screen and in
                // `localStorage`; failing to persist it is worth no
                // interruption here, and the next visit to the settings
                // page shows what the server actually holds.
            });
        });
    });

    // A click anywhere else, and Escape, both dismiss it.
    document.addEventListener("click", (event) => {
        if (!item.contains(event.target)) close();
    });
    item.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            close();
            trigger.focus();
        }
    });

}
