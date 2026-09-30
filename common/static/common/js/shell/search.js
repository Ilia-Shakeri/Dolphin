import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {registerPopover} from "dolphin/ui/popover.js";

/**
 * The topbar search box, on every page.
 *
 * One request per settled keystroke, not per keystroke: a debounce
 * (`SEARCH_DEBOUNCE_MS`) and a two-character floor together mean typing
 * a customer's name sends one query, not eleven. A sequence number
 * guards against the older of two overlapping answers painting last,
 * which is the classic search-box bug — type fast, and a slow reply for
 * "رض" arrives after the quick one for "رضا" and replaces it.
 *
 * Rows are shared with the reminder bell (`topbar-list-*`): the two
 * panels are the same list in the same dropdown, and only their content
 * differs.
 */
export function setupGlobalSearch() {
    const toggle = document.getElementById("global-search-toggle");
    const menu = document.getElementById("global-search-menu");
    if (!toggle || !menu) return;

    const input = document.getElementById("global-search-input");
    const body = document.getElementById("global-search-body");
    const empty = document.getElementById("global-search-empty");
    const errorNote = document.getElementById("global-search-error");
    const SEARCH_DEBOUNCE_MS = 250;
    const MIN_QUERY_LENGTH = 2;
    let timer = null;
    let sequence = 0;

    // Registered before anything else here uses `popover`, because the
    // `Ctrl/⌘+K` handler below opens it.
    const popover = registerPopover({
        toggle,
        panel: menu,
        // Opening a search box that is not focused is opening nothing.
        onOpen: () => input.focus(),
    });

    // `node` is `null` before typing starts — an empty box, not an
    // instructional message, product-owner decision 2026-09-08.
    function show(node) {
        [empty, errorNote].forEach((each) => { each.hidden = each !== node; });
    }

    function renderGroup(group) {
        const section = document.createElement("div");
        section.className = "topbar-list-group";

        const heading = document.createElement("div");
        heading.className = "d-flex align-items-center justify-content-between gap-2 px-2 mb-1";
        const left = document.createElement("span");
        left.className = "d-flex align-items-center gap-2";
        const icon = document.createElement("i");
        icon.className = `di-duotone ${group.icon} fs-5 text-${group.accent}`;
        for (let index = 1; index <= (group.icon_paths || 2); index += 1) {
            icon.append(searchPathSpan(index));
        }
        const label = document.createElement("span");
        label.className = "text-gray-700 fw-bold fs-8";
        label.textContent = `${group.label} (${toPersianDigits(String(group.count))})`;
        left.append(icon, label);
        heading.appendChild(left);

        // More matches than the group lists: the module's own page has
        // the real filters, so send the reader there rather than paging
        // a dropdown.
        if (group.count > group.items.length) {
            const more = document.createElement("a");
            more.className = "text-primary fw-semibold fs-8 text-decoration-none";
            more.href = group.list_url;
            more.textContent = "همه";
            heading.appendChild(more);
        }
        section.appendChild(heading);

        group.items.forEach((item) => {
            const link = document.createElement("a");
            link.className = "topbar-list-item";
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
        try {
            const data = await apiRequest(`/api/v1/search/?q=${encodeURIComponent(query)}`);
            // A stale answer must never paint over a newer one.
            if (mine !== sequence) return;
            body.replaceChildren();
            data.groups.forEach((group) => body.appendChild(renderGroup(group)));
            show(data.count ? null : empty);
        } catch (error) {
            if (mine !== sequence) return;
            body.replaceChildren();
            show(errorNote);
        }
    }

    input.addEventListener("input", () => {
        const query = input.value.trim();
        if (timer) clearTimeout(timer);
        if (query.length < MIN_QUERY_LENGTH) {
            // Abandon any answer still in flight, so it cannot arrive and
            // fill a box the user has just cleared.
            sequence += 1;
            body.replaceChildren();
            show(null);
            return;
        }
        timer = setTimeout(() => run(query), SEARCH_DEBOUNCE_MS);
    });

    // Enter opens the first result, which is what a search box is for
    // when the answer is already on screen.
    input.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        const first = body.querySelector(".topbar-list-item");
        if (first) {
            event.preventDefault();
            window.location.href = first.getAttribute("href");
        }
    });

    // Ctrl/⌘+K from anywhere, the shortcut a keyboard already expects
    // for a search box. Escape and outside-click are `registerPopover`'s,
    // shared with every other panel.
    document.addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
            event.preventDefault();
            popover.open();
            input.select();
        }
    });
}
