import {apiRequest} from "dolphin/core/api.js";
import {normalizeSearchText, toPersianDigits} from "dolphin/core/digits.js";
import {registerPopover} from "dolphin/ui/popover.js";

/**
 * The topbar search box, on every page.
 *
 * The magnifier *becomes* the field (2.40.1), the same motion as a board
 * column's own search (`setupBoardColumnSearch`): one box holds the icon
 * and the input, and only the box's width animates, so the header's height
 * never changes and the bell and user menu are pushed along rather than
 * covered. Results open in a panel under the field, as wide as the field.
 *
 * One request per settled keystroke, not per keystroke: a debounce
 * (`SEARCH_DEBOUNCE_MS`) and a two-character floor together mean typing
 * a customer's name sends one query, not eleven. A newer query aborts the
 * one still in flight, and a sequence number still guards against an
 * older answer painting last — type fast, and a slow reply for "رض" must
 * never replace the one for "رضا".
 *
 * Rows are shared with the reminder bell (`topbar-list-*`): the two
 * panels are the same list in the same dropdown, and only their content
 * differs.
 */
export function setupGlobalSearch() {
    const toggle = document.getElementById("global-search-toggle");
    const menu = document.getElementById("global-search-menu");
    const box = document.getElementById("global-search-box");
    if (!toggle || !menu || !box) return;

    const input = document.getElementById("global-search-input");
    const closer = document.getElementById("global-search-close");
    const body = document.getElementById("global-search-body");
    const empty = document.getElementById("global-search-empty");
    const errorNote = document.getElementById("global-search-error");
    const status = document.getElementById("global-search-status");
    const SEARCH_DEBOUNCE_MS = 250;
    const MIN_QUERY_LENGTH = 2;
    let timer = null;
    let sequence = 0;
    let inFlight = null;
    let active = -1;

    // Registered before anything else here uses `popover`, because the
    // `Ctrl/⌘+K` handler below opens it. The box counts as inside, so a
    // click in the field does not read as a click outside the panel.
    const popover = registerPopover({
        toggle,
        panel: menu,
        inside: box,
        onOpen: () => {
            box.classList.add("topbar-search-open");
            input.tabIndex = 0;
            closer.tabIndex = 0;
            // Opening a search box that is not focused is opening nothing.
            input.focus();
        },
        onClose: () => {
            box.classList.remove("topbar-search-open");
            input.tabIndex = -1;
            closer.tabIndex = -1;
            input.value = "";
            reset();
        },
    });

    // `node` is `null` before typing starts — an empty box, not an
    // instructional message, product-owner decision 2026-09-08. The panel
    // itself stays out of sight until there is something to show in it.
    function show(node) {
        [empty, errorNote].forEach((each) => { each.hidden = each !== node; });
        const idle = node === null && !body.childElementCount;
        menu.toggleAttribute("data-idle", idle);
        input.setAttribute("aria-expanded", String(!idle));
    }

    function announce(text) {
        status.textContent = text;
    }

    function reset() {
        if (timer) clearTimeout(timer);
        // Abandon any answer still in flight, so it cannot arrive and fill
        // a box the user has just cleared.
        sequence += 1;
        if (inFlight) inFlight.abort();
        inFlight = null;
        body.replaceChildren();
        setActive(-1);
        show(null);
        announce("");
    }

    function options() {
        return [...body.querySelectorAll(".topbar-list-item")];
    }

    function setActive(index) {
        const all = options();
        active = all.length ? Math.max(-1, Math.min(index, all.length - 1)) : -1;
        all.forEach((option, position) => {
            const on = position === active;
            option.classList.toggle("active", on);
            option.setAttribute("aria-selected", String(on));
            if (on) option.scrollIntoView({block: "nearest"});
        });
        if (active >= 0) input.setAttribute("aria-activedescendant", all[active].id);
        else input.removeAttribute("aria-activedescendant");
    }

    function renderGroup(group, groupIndex) {
        const section = document.createElement("div");
        section.className = "topbar-list-group";
        section.setAttribute("role", "group");

        const heading = document.createElement("div");
        heading.className = "d-flex align-items-center justify-content-between gap-2 px-2 mb-1";
        const left = document.createElement("span");
        left.className = "d-flex align-items-center gap-2";
        const icon = document.createElement("i");
        icon.className = `di-duotone ${group.icon} fs-5 text-${group.accent}`;
        icon.setAttribute("aria-hidden", "true");
        for (let index = 1; index <= (group.icon_paths || 2); index += 1) {
            icon.append(searchPathSpan(index));
        }
        const label = document.createElement("span");
        label.className = "text-gray-700 fw-bold fs-8";
        label.id = `global-search-group-${groupIndex}`;
        label.textContent = `${group.label} (${toPersianDigits(String(group.count))})`;
        section.setAttribute("aria-labelledby", label.id);
        left.append(icon, label);
        heading.appendChild(left);

        // More matches than the group lists: the module's own page has
        // the real filters, so send the reader there rather than paging
        // a dropdown.
        if (group.count > group.items.length) {
            const more = document.createElement("a");
            more.className = "text-primary fw-semibold fs-8 text-decoration-none";
            more.href = group.list_url;
            more.tabIndex = -1;
            more.textContent = "همه";
            more.setAttribute("aria-label", `همهٔ ${group.label}`);
            heading.appendChild(more);
        }
        section.appendChild(heading);

        group.items.forEach((item, itemIndex) => {
            const link = document.createElement("a");
            link.className = "topbar-list-item";
            link.id = `global-search-option-${groupIndex}-${itemIndex}`;
            link.setAttribute("role", "option");
            link.setAttribute("aria-selected", "false");
            link.tabIndex = -1;
            link.href = item.url;
            const text = document.createElement("span");
            text.className = "flex-grow-1 min-w-0";
            const title = document.createElement("span");
            title.className = "d-block text-gray-900 fw-semibold fs-7 text-truncate";
            title.textContent = item.title;
            const subtitle = document.createElement("span");
            subtitle.className = "d-block text-muted fs-8 text-truncate";
            subtitle.textContent = item.subtitle;
            text.append(title, subtitle);
            link.appendChild(text);
            section.appendChild(link);
        });
        return section;
    }

    function searchPathSpan(index) {
        const span = document.createElement("span");
        span.className = `path${index}`;
        return span;
    }

    async function run(query) {
        const mine = ++sequence;
        if (inFlight) inFlight.abort();
        const controller = new AbortController();
        inFlight = controller;
        try {
            const data = await apiRequest(
                `/api/v1/search/?q=${encodeURIComponent(query)}`,
                {signal: controller.signal},
            );
            // A stale answer must never paint over a newer one.
            if (mine !== sequence) return;
            inFlight = null;
            body.replaceChildren();
            data.groups.forEach((group, index) => body.appendChild(renderGroup(group, index)));
            setActive(-1);
            show(data.count ? null : empty);
            announce(data.count ? `${toPersianDigits(String(data.count))} نتیجه` : "چیزی پیدا نشد.");
        } catch (error) {
            if (mine !== sequence) return;
            inFlight = null;
            body.replaceChildren();
            setActive(-1);
            show(errorNote);
            announce("جست‌وجو ممکن نشد.");
        }
    }

    input.addEventListener("input", () => {
        const query = normalizeSearchText(input.value).trim();
        if (timer) clearTimeout(timer);
        if (query.length < MIN_QUERY_LENGTH) {
            reset();
            return;
        }
        timer = setTimeout(() => run(query), SEARCH_DEBOUNCE_MS);
    });

    // ↑ ↓ move through the results, Enter opens the highlighted one — or
    // the first, which is what a search box is for when the answer is
    // already on screen. Escape is `registerPopover`'s, shared with every
    // other panel, and hands focus back to the magnifier.
    input.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            const count = options().length;
            if (!count) return;
            event.preventDefault();
            const step = event.key === "ArrowDown" ? 1 : -1;
            setActive(active < 0 && step < 0 ? count - 1 : (active + step + count) % count);
            return;
        }
        if (event.key !== "Enter") return;
        const chosen = options()[active] || body.querySelector(".topbar-list-item");
        if (chosen) {
            event.preventDefault();
            window.location.href = chosen.getAttribute("href");
        }
    });

    closer.addEventListener("click", (event) => {
        event.stopPropagation();
        popover.close();
        toggle.focus();
    });

    // Leaving an empty field folds it away; leaving one with a query in it
    // keeps it, so a reader who tabs out to check something loses nothing.
    box.parentElement.addEventListener("focusout", (event) => {
        if (box.parentElement.contains(event.relatedTarget)) return;
        if (!input.value.trim() && popover.isOpen()) popover.close();
    });

    // Ctrl/⌘+K from anywhere, the shortcut a keyboard already expects
    // for a search box.
    document.addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
            event.preventDefault();
            popover.open();
            input.select();
        }
    });

    show(null);
}
