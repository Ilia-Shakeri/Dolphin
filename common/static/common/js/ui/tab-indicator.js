/**
 * A sliding indicator under line tabs (2.40.38).
 *
 * The UI kit marks the active tab with its own bottom border, which jumps
 * from tab to tab. One bar per tab row now slides to the active tab and takes
 * its width, so a switch reads as a movement between places. It follows the
 * `active` class wherever that is set (`ui/profile-tabs.js`, the theme's own
 * tabs) and the row's size.
 */
export function setupTabIndicators(root = document) {
    root.querySelectorAll(".nav-line-tabs:not(.has-indicator)").forEach((nav) => {
        const bar = document.createElement("li");
        bar.className = "nav-line-indicator";
        bar.setAttribute("aria-hidden", "true");
        bar.setAttribute("role", "presentation");
        nav.classList.add("has-indicator");
        nav.append(bar);
        const place = () => {
            const active = nav.querySelector(".nav-link.active");
            if (!active) { bar.style.width = "0"; return; }
            const box = nav.getBoundingClientRect();
            const link = active.getBoundingClientRect();
            // Measured from the row's start edge, which is its right in RTL.
            const offset = getComputedStyle(nav).direction === "rtl" ? link.right - box.right : link.left - box.left;
            bar.style.width = `${link.width}px`;
            bar.style.transform = `translateX(${offset}px)`;
        };
        place();
        requestAnimationFrame(() => bar.classList.add("is-ready"));
        new MutationObserver(place).observe(nav, {attributes: true, attributeFilter: ["class"], subtree: true});
        if (typeof ResizeObserver === "function") new ResizeObserver(place).observe(nav);
        document.fonts?.ready.then(place);
    });
}
