/* --- the shared popover -------------------------------------------------

   One open/close behaviour for every panel in this shell that hangs off a
   button: the header user menu, global search, the reminder bell and each
   list card's own filter panel.

   All four already behaved *almost* the same, because each was written by
   copying the one before it — four `setOpen`s, four document-level click
   listeners and four document-level keydown listeners, differing in small
   ways nobody intended (search closed on `event.target !== toggle`, the
   filter panel also checked `toggle.contains(event.target)`, so a click on
   the icon *inside* the search button closed the menu it had just opened).

   And none of them knew about the others. The product owner hit the
   consequence directly: «وقتی منوی یادآورها باز است و روی جست‌وجو کلیک
   می‌کنیم، منوی جدید نباید زیر منوی قبلی باز شود — قبلی باید بسته شود»
   (2026-09-20). One registry fixes that by construction — opening any
   popover closes whichever other one is open, because they all go through
   here.

   Two document listeners in total rather than two per popover, for the
   same reason: the outside-click rule is one rule about the page, not a
   rule each panel owns a copy of. */

//: Every registered popover, in registration order. Small and stable —
//: three from the shell plus one per list card — so a plain array is the
//: right shape and the iteration cost is nothing.
const openablePopovers = [];

/**
 * Register one button/panel pair.
 *
 * A panel is shown by adding the theme's own `show` class, or — with
 * `useHidden` — by clearing the `hidden` attribute. Two mechanisms
 * because the shell genuinely has two: the three topbar menus are the
 * theme's dropdowns and are styled off `.show`, while a list card's
 * filter panel is ordinary markup that was never given a `.show` rule.
 * Converting the second to the first is a visual change this item did
 * not ask for, so the component knows about both rather than the page
 * keeping its own copy of the behaviour.
 *
 * `onOpen`/`onClose` are optional — the search box focuses its input,
 * the bell fetches its list.
 *
 * Returns `{open, close, flip, isOpen}` for the callers that close the
 * panel themselves, such as a filter form on submit.
 */
export function registerPopover({toggle, panel, onOpen, onClose, useHidden = false}) {
    if (!toggle || !panel) return null;

    const isOpen = useHidden
        ? () => !panel.hidden
        : () => panel.classList.contains("show");

    const entry = {
        toggle,
        panel,
        isOpen,
        open: () => setOpen(true),
        close: () => setOpen(false),
        flip: () => setOpen(!isOpen()),
    };

    function setOpen(open) {
        if (open) closeOtherPopovers(entry);
        if (useHidden) panel.hidden = !open;
        else panel.classList.toggle("show", open);
        toggle.setAttribute("aria-expanded", String(open));
        if (open) { if (onOpen) onOpen(); }
        else if (onClose) onClose();
    }

    toggle.addEventListener("click", (event) => {
        event.stopPropagation();
        entry.flip();
    });
    openablePopovers.push(entry);
    return entry;
}

/** Close every open popover except `keep`. */
function closeOtherPopovers(keep) {
    openablePopovers.forEach((entry) => {
        if (entry !== keep && entry.isOpen()) entry.close();
    });
}

/**
 * The two page-level rules, bound once for all of them.
 *
 * A click counts as "inside" when it lands in the panel *or* anywhere in
 * the button, icon and badge included — the bug the four copies disagreed
 * about was exactly this: three of them compared `event.target !== toggle`,
 * which is false for the `<i>` inside the toggle, so clicking the glyph
 * rather than the button's padding closed the menu the same click was
 * opening.
 */
export function setupPopoverDismissal() {
    document.addEventListener("click", (event) => {
        openablePopovers.forEach((entry) => {
            if (!entry.isOpen()) return;
            if (entry.panel.contains(event.target)) return;
            if (entry.toggle.contains(event.target)) return;
            entry.close();
        });
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        const open = openablePopovers.filter((entry) => entry.isOpen());
        if (!open.length) return;
        // Focus goes back to the button that opened it, which is where a
        // keyboard reader was before the panel took over.
        open.forEach((entry) => { entry.close(); entry.toggle.focus(); });
    });
}

/**
 * A list card's own "فیلتر" panel.
 *
 * `registerPopover` like every other panel in the shell, in its
 * `useHidden` mode: this one is plain markup toggled with the `hidden`
 * attribute rather than one of the theme's `.show`-styled dropdowns.
 * `toggle` carries `aria-expanded`, and
 * `.list-filter-toggle[aria-expanded="true"]` in dolphin.css gives it the
 * pressed look DolphinMenu's own `.show` would have.
 *
 * The panel's own form still submits normally (`setupPagedList`'s own
 * `form.addEventListener("submit", ...)` above) — only the search box
 * beside this button went live; everything in here stays an explicit
 * "اعمال" the reader chooses, since these are heavier filters (a status,
 * a date window) a reader is still composing keystroke by keystroke.
 */
export function setupListFilter(key) {
    const popover = registerPopover({
        toggle: document.getElementById(`${key}-filter-toggle`),
        panel: document.getElementById(`${key}-filter-panel`),
        useHidden: true,
    });
    if (!popover) return;
    // Applying a filter closes the panel — the reader chose one, no
    // reason to keep it open over the now-refreshed list.
    popover.panel.querySelector("form")
        ?.addEventListener("submit", () => popover.close());
}

/**
 * Every list page's filter row, collapsed behind a header button that
 * opens a dropdown panel — the purchased theme's own filter pattern
 * (the vendor demo's own customers list page — its "فیلتر" button + its
 * `.menu.menu-sub.menu-sub-dropdown` panel), applied generically rather
 * than rebuilt per page.
 *
 * Twenty-five templates carry `<form class="list-filters">`, each with
 * its own fields and its own `setupPagedList({form, ...})` submit
 * listener already attached directly to that form element. This moves
 * the existing form node — never clones it — into a new panel, so every
 * one of those listeners, and every input's id the page's own script
 * reads by `getElementById`, survives untouched; `getElementById` finds
 * an element wherever it sits in the document, so nothing about *where*
 * the form now lives affects any lookup already written against it.
 *
 * Opened and closed the same hand-rolled way as the reminder bell, the
 * search box and the user menu — `.show`, not `data-dolphin-menu-trigger` —
 * for the same reason all three of those are: `DolphinMenu` positions its
 * panel with Popper, and Popper lives in the plugins bundle this
 * deployment does not load.
 */
export function setupListFilterPopovers() {
    document.querySelectorAll("form.list-filters").forEach((form) => {
        const anchor = document.createElement("div");
        anchor.className = "list-filters-popover position-relative d-inline-block";

        const toggle = document.createElement("button");
        toggle.type = "button";
        // Icon-only — the same `.btn-icon.btn-light-primary` shape every
        // other list page's own hand-built filter button already uses
        // (`.list-filter-toggle`, e.g. `leads/list.html`). This one used
        // to carry the word «فیلتر» beside the icon; measured against
        // the rest of the panel, that made the twenty-five pages built
        // through this generic popover read differently from every page
        // with a hand-built filter button (product-owner request
        // 2026-09-12). `aria-label` keeps the same word for anyone who
        // cannot see the icon.
        toggle.className = "btn btn-icon btn-light-primary";
        toggle.setAttribute("aria-haspopup", "true");
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "فیلتر");
        // Named after the form it opens, since the form's own id is the
        // one stable thing about it that already varies meaningfully
        // page to page — a test or a future script can find "the filter
        // button for the product list" without this module inventing a
        // second id for the same relationship.
        if (form.id) toggle.dataset.filterToggleFor = form.id;
        const icon = document.createElement("i");
        icon.className = "di-duotone di-filter fs-3";
        icon.append(document.createElement("span"), document.createElement("span"));
        icon.children[0].className = "path1";
        icon.children[1].className = "path2";
        toggle.append(icon);

        const panel = document.createElement("div");
        panel.className = "menu menu-sub menu-sub-dropdown menu-column w-300px w-md-350px list-filters-panel";
        const header = document.createElement("div");
        header.className = "px-6 py-4 fs-5 fw-bold text-gray-900";
        header.textContent = "فیلتر";
        const separator = document.createElement("div");
        separator.className = "separator border-gray-200";
        const body = document.createElement("div");
        body.className = "px-6 py-5";
        panel.append(header, separator, body);

        form.parentElement.insertBefore(anchor, form);
        anchor.append(toggle, panel);
        body.appendChild(form);
        form.classList.add("mb-0");

        // The theme's own filter panel pairs "ریست" beside "تایید" in one
        // row; these forms only ever shipped the one submit button, so
        // the reset button is built here rather than in twenty-five
        // templates. A native `type="reset"` needs no per-page knowledge
        // of which fields exist — the browser already knows how to put a
        // form back to its own defaults.
        const submit = form.querySelector(".list-filters-submit, button[type='submit']");
        if (submit) {
            const actions = document.createElement("div");
            actions.className = "d-flex justify-content-end gap-2";
            const reset = document.createElement("button");
            reset.type = "reset";
            reset.className = "btn btn-light";
            reset.textContent = "بازنشانی";
            submit.replaceWith(actions);
            actions.append(reset, submit);
        }

        const popover = registerPopover({toggle, panel});
        // Closes the popover on a successful apply, matching the theme's
        // own `data-dolphin-menu-dismiss` on its filter panel's submit button.
        form.addEventListener("submit", () => popover.close());
        // A native reset only restores the fields; nothing here re-asks
        // for the now-default list on its own. Resubmitting after the
        // browser's own reset has already run — not before it — is what
        // makes "بازنشانی" behave like "clear the filters and reload"
        // rather than "clear the filters, and reload whenever something
        // else happens to next."
        form.addEventListener("reset", () => setTimeout(() => form.requestSubmit()));
    });
}
