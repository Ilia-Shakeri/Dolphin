import {STATUS_ACCENTS} from "dolphin/core/labels.js";
import {bindLiveSearch} from "dolphin/ui/lists.js";

/**
 * Tint each Kanban column with the accent its own status already wears
 * everywhere else (product-owner request 2026-09-19: «هاله رنگی شبیه به
 * وضعیتش»).
 *
 * `STATUS_ACCENTS` is the single table this product paints statuses from —
 * the badges in every document list read it, and so does `statusBadge`.
 * Reusing it here is what makes the board agree with the table: the
 * column a cancelled lead sits in is the same red its row would be. No
 * per-board colour list is declared, so a status added to that table is
 * coloured on the boards too without touching this function.
 *
 * The attribute carries the accent *name*; `dolphin.css` §7 turns it into
 * the theme's own `--bs-<accent>` tokens, which are redefined in dark
 * mode — so the halo follows the theme rather than being a fixed colour
 * written into JavaScript.
 */
/**
 * A board card's top line: its name, and the control that says the card
 * opens something.
 *
 * The whole card has always been clickable (`jKanban`'s own `click`
 * option navigates to the detail page), so the old «مشاهدهٔ جزئیات» link
 * at the bottom was never the only way in — it was a text label repeating
 * what the card already did, on every card, in a 300px column where
 * vertical space is the scarce thing. Replaced by one quiet glyph in the
 * corner that names itself on hover (product-owner request 2026-09-20).
 *
 * Still a real `<a href>`, not a decorative span: it keeps the card
 * reachable by keyboard and openable in a new tab, neither of which the
 * div-with-a-click-handler underneath it offers. `title` carries the
 * hover text rather than a Bootstrap tooltip — jKanban writes these cards
 * in as an HTML string, so anything needing per-element initialisation
 * would have to be re-run on every render and after every drop.
 */
export function boardCardHeader(titleText, href) {
    const head = document.createElement("div");
    head.className = "kanban-card-head";

    const title = document.createElement("div");
    title.className = "kanban-card-title";
    title.textContent = titleText;

    const more = document.createElement("a");
    more.className = "kanban-card-more";
    more.href = href;
    more.title = "مشاهدهٔ جزئیات";
    more.setAttribute("aria-label", "مشاهدهٔ جزئیات");
    // The theme's *solid* glyph, not the duotone one: duotone draws two
    // of the three dots at 30% opacity, which read as one faint dot
    // (product owner, 2026-09-28: «باید بولد و واضح‌تر باشد»).
    const icon = document.createElement("i");
    icon.className = "di-solid di-dots-vertical fs-2";
    icon.setAttribute("aria-hidden", "true");
    more.append(icon);

    head.append(title, more);
    return head;
}

/**
 * Lets the three-dot "view details" link inside a board card actually
 * navigate.
 *
 * jKanban's own vendor bundle attaches a click listener directly to
 * every `.kanban-item` it builds (`function r(t,n)` in
 * `jkanban.bundle.js`), and that listener calls the DOM event's
 * `preventDefault()` unconditionally, before doing anything else — a
 * card used to have nothing inside it a browser would navigate by
 * default, so this was harmless. `boardCardHeader`'s anchor changed
 * that: `preventDefault` on the click stops the anchor's own navigation
 * too, since a link's default action resolves only after the event has
 * finished propagating. Every card's three-dot control looked wired up
 * — a real `<a href>`, reachable by keyboard — and silently did nothing
 * when pressed (product owner, 2026-09-21: «سه نقطه مشاهده جزئیات در
 * تابلوها و کارت‌ها کار نمیکند»).
 *
 * Not fixed inside `boardCardHeader` itself: a card is built as an HTML
 * *string* (`cardContent`'s `wrap.innerHTML`), and jKanban re-parses
 * that string into fresh nodes via its own `innerHTML =`, which drops
 * any listener that was attached to the nodes which produced the
 * string. A listener has to live on something that survives — the
 * stable board container — and has to run in the *capture* phase, so it
 * sees the click before it reaches jKanban's own bubble-phase listener
 * down on `.kanban-item`. Stopping propagation there does not touch
 * dragula's own drag detection, which listens for `mousedown`/
 * `mousemove`, never `click`.
 */
export function letCardDetailsLinkThrough(container) {
    container.addEventListener("click", (event) => {
        if (event.target.closest(".kanban-card-more")) event.stopPropagation();
    }, true);
}

export function paintBoardColumns(container, statuses) {
    statuses.forEach((status) => {
        const board = container.querySelector(`.kanban-board[data-id="${status}"]`);
        if (board) board.dataset.accent = STATUS_ACCENTS[status] || "secondary";
    });
}

/**
 * One board column's own search, collapsed behind a small icon button in
 * that column's header (product-owner decision 2026-09-09).
 *
 * Shared by both boards below because the shape is identical: a toggle
 * appended into jKanban's own `.kanban-title-board`, and one input
 * revealed between that header and the column's card list. `onSearch`
 * receives the trimmed term and refetches that column alone; the term
 * goes to the same DRF `search=` the list page's own box already uses, so
 * a column searches exactly the fields its list searches (leads:
 * customer name, source, campaign, notes — orders: number, customer,
 * notes, and each line's product name) with no new backend surface.
 *
 * Collapsed by default on purpose: four permanently-open search boxes
 * across a four-column board would crowd out the cards they filter.
 */
export function setupBoardColumnSearch(container, status, onSearch) {
    const board = container.querySelector(`.kanban-board[data-id="${status}"]`);
    const title = board?.querySelector(".kanban-title-board");
    const drag = board?.querySelector(".kanban-drag");
    if (!board || !title || !drag) return;

    // One element, not two: the magnifier and the field are the same box,
    // which is what lets the icon *become* the field instead of a second
    // row appearing under the header and pushing every card down
    // (product-owner request 2026-09-20). Width is what animates — from a
    // square the size of the icon to the width of the header — so the
    // header's own height never changes and the cards never move.
    const search = document.createElement("div");
    search.className = "board-search";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "btn btn-icon btn-sm btn-active-light-primary board-search-toggle";
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "جست‌وجو در این ستون");
    const icon = document.createElement("i");
    icon.className = "di-duotone di-magnifier fs-5";
    ["path1", "path2"].forEach((name) => {
        const path = document.createElement("span");
        path.className = name;
        icon.append(path);
    });
    toggle.append(icon);

    const input = document.createElement("input");
    input.type = "search";
    input.className = "board-search-input";
    input.placeholder = "جست‌وجو…";
    input.setAttribute("aria-label", "جست‌وجو در این ستون");
    // `tabindex="-1"` while closed so a keyboard reader tabbing along the
    // header lands on the button, not on a field that is zero pixels wide.
    input.tabIndex = -1;

    search.append(toggle, input);
    title.append(search);

    function close({clear = true} = {}) {
        if (!search.classList.contains("board-search-open")) return;
        search.classList.remove("board-search-open");
        toggle.setAttribute("aria-expanded", "false");
        input.tabIndex = -1;
        // Closing clears the filter: leaving a column silently filtered by
        // a term nobody can see any more is the one way this control could
        // lie about what the board contains.
        if (clear && input.value) {
            input.value = "";
            onSearch("");
        }
    }

    function open() {
        search.classList.add("board-search-open");
        toggle.setAttribute("aria-expanded", "true");
        input.tabIndex = 0;
        input.focus();
    }

    toggle.addEventListener("click", (event) => {
        event.stopPropagation();
        if (search.classList.contains("board-search-open")) close(); else open();
    });

    // Anywhere outside this one search closes it. Registered on the
    // document rather than on the board, because "anywhere on the page"
    // is what was asked for — and `search.contains` is what keeps a click
    // on the field itself (or on its own clear button) from closing it.
    document.addEventListener("click", (event) => {
        if (!search.contains(event.target)) close();
    });
    // Escape closes it too, which is what a person who opened it by
    // accident reaches for first.
    input.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            close();
            toggle.focus();
        }
    });

    bindLiveSearch(input, () => onSearch(input.value.trim()));
}
