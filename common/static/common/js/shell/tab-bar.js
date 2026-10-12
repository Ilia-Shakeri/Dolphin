/**
 * The phone's tab bar (2.40.38).
 *
 * On a phone the panel's navigation was a menu behind the header's
 * hamburger; the platform puts the few destinations people return to all day
 * in a bar at the bottom, one tap away. The bar is built from the sidebar the
 * server already rendered for this reader, so it offers only pages this
 * reader may open on this deployment — a destination the sidebar does not
 * carry is simply not in the bar — and «بیشتر» opens the full menu.
 */

const DESTINATIONS = ["/", "/customers/", "/leads/", "/invoices/"];

function iconFor(link) {
    const own = link.querySelector(".menu-icon i");
    const group = link.closest(".menu-accordion")?.querySelector(":scope > .menu-link .menu-icon i");
    return (own || group)?.cloneNode(true) || null;
}

function tab(element, icon, label) {
    if (icon) element.append(icon);
    const text = document.createElement("span");
    text.textContent = label;
    element.append(text);
    return element;
}

export function setupTabBar() {
    const sidebar = document.getElementById("app-sidebar");
    const toggle = document.getElementById("nav-toggle");
    if (!sidebar || !toggle) return;
    const links = DESTINATIONS
        .map((path) => sidebar.querySelector(`a.menu-link[href="${path}"]`))
        .filter(Boolean);
    if (links.length < 2) return;

    const bar = document.createElement("nav");
    bar.className = "dolphin-tab-bar";
    bar.setAttribute("aria-label", "راهبری سریع");
    const path = document.body.dataset.navMatch || window.location.pathname;
    const current = links
        .filter((link) => {
            const href = link.getAttribute("href");
            return href === "/" ? path === "/" : path.startsWith(href);
        })
        .sort((a, b) => b.getAttribute("href").length - a.getAttribute("href").length)[0];
    links.forEach((link) => {
        const anchor = document.createElement("a");
        anchor.href = link.getAttribute("href");
        if (link === current) anchor.setAttribute("aria-current", "page");
        bar.append(tab(anchor, iconFor(link), link.querySelector(".menu-title")?.textContent.trim() || link.textContent.trim()));
    });
    const more = document.createElement("button");
    more.type = "button";
    more.setAttribute("aria-controls", "app-sidebar");
    const dots = document.createElement("i");
    dots.className = "di-duotone di-dots-horizontal";
    dots.setAttribute("aria-hidden", "true");
    for (let index = 1; index <= 3; index += 1) dots.appendChild(document.createElement("span")).className = `path${index}`;
    bar.append(tab(more, dots, "بیشتر"));
    // The header's own toggle opens the drawer, so the theme's drawer keeps
    // its overlay, swipe and focus handling.
    more.addEventListener("click", () => toggle.click());

    document.body.append(bar);
    document.body.classList.add("has-tab-bar");
}
