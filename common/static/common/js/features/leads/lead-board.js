import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {LEAD_STATUS_LABELS} from "dolphin/core/labels.js";
import {errorText, globalMessage, showError} from "dolphin/core/messages.js";
import {boardCardHeader, letCardDetailsLinkThrough, paintBoardColumns, setupBoardColumnSearch} from "dolphin/ui/boards.js";

/**
 * The leads Kanban board — the same three real `Lead.status` values
 * (`LEAD_STATUS_LABELS` above, the ordinary list's own badge map) as
 * fixed columns, drawn with the theme's own `jkanban` bundle (dragula
 * under it) rather than a hand-rolled drag-and-drop implementation.
 *
 * Every card comes from `leads_for(user)` through the ordinary
 * `/api/v1/leads/?status=` endpoint, one paginated request per column —
 * the same scope and the same rows the list page and the calendar would
 * show for the same reader. Dropping a card into another column PATCHes
 * that same lead through `/api/v1/leads/<id>/`, the very endpoint the
 * calendar's own drag already uses for a different field, so this adds
 * no new mutation path: `LeadSerializer.update` -> `sales.services.
 * update_lead` still validates the status, still locks the actor, still
 * refuses a sales agent a lead outside their own scope.
 */
export async function setupLeadBoard() {
    const container = document.getElementById("lead-board");
    if (!container || typeof jKanban === "undefined") return;
    letCardDetailsLinkThrough(container);
    const loading = document.getElementById("lead-board-loading");
    const errorNode = document.getElementById("lead-board-error");
    const canManage = container.dataset.canManageLeads === "true";

    // pending/completed/cancelled, same order `LEAD_STATUS_LABELS` and
    // the calendar legend already use.
    const STATUSES = Object.keys(LEAD_STATUS_LABELS);
    // Where the next page for each column's own "load more" comes from,
    // and whether that column has anything at all — kept outside jKanban
    // itself, which has no paging concept of its own.
    const pageState = {};

    function boardTitle(status, count) {
        const [label] = LEAD_STATUS_LABELS[status];
        const wrap = document.createElement("div");
        wrap.className = "d-flex align-items-center gap-2";
        const text = document.createElement("span");
        text.textContent = label;
        const badge = document.createElement("span");
        badge.className = "badge badge-light-secondary";
        badge.textContent = toPersianDigits(String(count));
        wrap.append(text, badge);
        return wrap.innerHTML;
    }

    /**
     * Every piece of text below goes through `textContent`; `innerHTML`
     * is read once, at the end, only because jKanban's own API takes an
     * item's content as an HTML string — the same escape-then-serialise
     * pattern `buildEventPopoverContent` above already uses for the same
     * reason with Bootstrap's Popover.
     */
    function cardContent(lead) {
        const wrap = document.createElement("div");

        wrap.append(boardCardHeader(
            lead.customer_name || lead.source || `سرنخ #${toPersianDigits(String(lead.id))}`,
            `/leads/${lead.id}/`,
        ));

        if (lead.assigned_to_display) {
            const row = document.createElement("div");
            row.className = "d-flex align-items-center gap-2 mb-2";
            const symbol = document.createElement("span");
            symbol.className = "symbol symbol-25px symbol-circle";
            const symbolLabel = document.createElement("span");
            const colors = ["primary", "success", "info", "warning", "danger"];
            const color = colors[Math.abs(Number(lead.assigned_to)) % colors.length];
            symbolLabel.className = `symbol-label bg-light-${color} text-${color} fw-bold fs-8`;
            symbolLabel.textContent = lead.assigned_to_display.trim().charAt(0);
            symbol.append(symbolLabel);
            const name = document.createElement("span");
            name.className = "fs-8 text-gray-700";
            name.textContent = lead.assigned_to_display;
            row.append(symbol, name);
            wrap.append(row);
        }

        [
            ["منبع", lead.source],
            ["کمپین", lead.campaign_or_batch],
        ].forEach(([label, value]) => {
            if (!value) return;
            const row = document.createElement("div");
            row.className = "fs-8 text-gray-600 mb-1";
            row.textContent = `${label}: ${value}`;
            wrap.append(row);
        });

        if (lead.next_follow_up_at) {
            const row = document.createElement("div");
            row.className = "fs-8 text-gray-600 mb-1";
            row.textContent = `پیگیری بعدی: ${displayDate(lead.next_follow_up_at)}`;
            wrap.append(row);
        }

        return wrap.innerHTML;
    }

    function toItem(lead) {
        return {id: String(lead.id), title: cardContent(lead)};
    }

    function boardElement(status) {
        return container.querySelector(`.kanban-board[data-id="${status}"] .kanban-drag`);
    }

    // Kept alongside the DOM rather than re-read from it: the badge text
    // is Persian digits, and counting from a known number is simpler and
    // less fragile than parsing them back out on every drop.
    const counts = {};

    function updateBoardCount(status, delta) {
        counts[status] += delta;
        const badge = container.querySelector(
            `.kanban-board[data-id="${status}"] .kanban-title-board .badge`,
        );
        if (badge) badge.textContent = toPersianDigits(String(counts[status]));
    }

    function renderLoadMore(status) {
        const drag = boardElement(status);
        if (!drag) return;
        drag.querySelector(".lead-board-load-more")?.remove();
        const state = pageState[status];
        if (!state?.next) return;
        const button = document.createElement("button");
        button.type = "button";
        // `not-draggable`: jkanban.bundle.js cancels a drag started on any
        // element carrying this class, the same mechanism its own
        // add-item footer uses — not a real kanban item, so it must not
        // behave like one.
        button.className = "btn btn-sm btn-light-primary w-100 not-draggable lead-board-load-more";
        button.textContent = "بارگذاری بیشتر";
        button.addEventListener("click", () => loadMore(status));
        drag.append(button);
    }

    function renderEmptyState(status) {
        const drag = boardElement(status);
        if (!drag || drag.querySelector(".kanban-item")) return;
        const empty = document.createElement("div");
        empty.className = "not-draggable lead-board-empty text-center fs-8 py-6";
        empty.textContent = pageState[status]?.search
            ? "سرنخی با این جست‌وجو در این ستون نیست."
            : "سرنخی در این وضعیت نیست.";
        drag.append(empty);
    }

    function columnUrl(status, page) {
        const term = pageState[status]?.search;
        const search = term ? `&search=${encodeURIComponent(term)}` : "";
        return `/api/v1/leads/?status=${status}&ordering=-created_at&page=${page}${search}`;
    }

    async function loadMore(status) {
        const state = pageState[status];
        if (!state?.next) return;
        try {
            const data = await apiRequest(state.next);
            data.results.forEach((lead) => kanban.addElement(status, toItem(lead)));
            state.next = data.next;
            renderLoadMore(status);
        } catch (error) {
            showError(error);
        }
    }

    /**
     * Refetch one column from page 1 under its own search term. The card
     * list is emptied and rebuilt rather than filtered in place: the term
     * is applied by the server across the whole column, not just the page
     * already loaded, so hiding local cards would under-report every match
     * past the first page.
     */
    async function reloadColumn(status, term) {
        const drag = boardElement(status);
        if (!drag) return;
        pageState[status] = {...pageState[status], search: term};
        try {
            const data = await apiRequest(columnUrl(status, 1));
            drag.innerHTML = "";
            data.results.forEach((lead) => kanban.addElement(status, toItem(lead)));
            pageState[status] = {next: data.next, search: term};
            counts[status] = data.count;
            const badge = container.querySelector(
                `.kanban-board[data-id="${status}"] .kanban-title-board .badge`,
            );
            if (badge) badge.textContent = toPersianDigits(String(data.count));
            renderLoadMore(status);
            renderEmptyState(status);
        } catch (error) {
            showError(error);
        }
    }

    let kanban;

    loading.hidden = false;
    errorNode.hidden = true;
    container.hidden = true;
    try {
        const pages = await Promise.all(
            STATUSES.map((status) =>
                apiRequest(`/api/v1/leads/?status=${status}&ordering=-created_at&page=1`),
            ),
        );
        loading.hidden = true;
        container.hidden = false;

        const boards = STATUSES.map((status, index) => {
            const data = pages[index];
            pageState[status] = {next: data.next};
            counts[status] = data.count;
            // No `dragTo` restriction: nothing in `_validate_lead_status`
            // (sales/services.py) restricts which of the three statuses a
            // lead may move to from which, so every column accepts a drop
            // from every other one — jKanban's own default when `dragTo`
            // is left unset.
            return {
                id: status,
                title: boardTitle(status, data.count),
                item: data.results.map(toItem),
            };
        });

        container.dataset.canDrag = String(canManage);
        kanban = new jKanban({
            element: "#lead-board",
            gutter: "0.75rem",
            widthBoard: "300px",
            // Not `responsivePercentage`: reading jkanban.bundle.js shows
            // it unconditionally overwrites `gutter` to a hard-coded
            // `"1%"` the moment this is on, silently ignoring whatever
            // `gutter` above says — measured directly (computed
            // `margin-right` stayed a nonzero percentage no matter what
            // `gutter` was set to). Narrow-viewport stacking is handled
            // in CSS instead: `#lead-board .kanban-board`'s own
            // `max-width: 767.98px` rule in dolphin.css forces full width
            // with `!important`, the only way to beat this inline style.
            dragBoards: false,
            dragItems: canManage,
            boards,
            // No `click` handler, deliberately. The whole card used to
            // navigate, which made every attempt to start a drag a
            // coin-flip between moving the card and leaving the page —
            // and on a touch screen there is no way to express "press
            // but do not tap". The three-dot control in the corner is
            // now the only way in (product owner, 2026-09-20: «کلیک روی
            // بدنه کارت نباید جزئیات را باز کند»), and it is a real
            // `<a href>`, so it works with the keyboard, with a middle
            // click and with "open in new tab" — none of which the
            // `window.location` this replaced ever did.
            dropEl: async (el, target, source) => {
                const leadId = el.dataset.eid;
                const toStatus = target.parentNode.dataset.id;
                const fromStatus = source.parentNode.dataset.id;
                if (toStatus === fromStatus) return;
                try {
                    await apiRequest(`/api/v1/leads/${leadId}/`, {
                        method: "PATCH",
                        body: {status: toStatus},
                    });
                    globalMessage("وضعیت سرنخ به‌روزرسانی شد.", true);
                    updateBoardCount(fromStatus, -1);
                    updateBoardCount(toStatus, 1);
                    renderEmptyState(fromStatus);
                    renderEmptyState(toStatus);
                } catch (error) {
                    // dragula has already moved the node into `target`
                    // by the time this fires; a rejected PATCH must move
                    // it back, the same revert `setupLeadCalendar`'s own
                    // `eventDrop` performs with `info.revert()` above —
                    // jKanban carries no equivalent, so this does the
                    // same thing by hand.
                    source.append(el);
                    renderEmptyState(fromStatus);
                    renderEmptyState(toStatus);
                    showError(error);
                }
            },
        });

        paintBoardColumns(container, STATUSES);

        STATUSES.forEach((status) => {
            // A fixed number of cards shows before a column scrolls
            // internally instead of stretching the whole board — see the
            // `.kanban-drag` max-height rule in dolphin.css. The class is
            // the theme's own overlay scrollbar (vendor `_scroll.scss`),
            // the same one the app sidebar itself scrolls with, not a
            // hand-rolled one — it stays invisible until hovered, so a
            // short column shows no scrollbar chrome at all.
            boardElement(status)?.classList.add("dolphin-hover-scroll");
            renderLoadMore(status);
            renderEmptyState(status);
            setupBoardColumnSearch(container, status, (term) => reloadColumn(status, term));
        });
    } catch (error) {
        loading.hidden = true;
        errorNode.textContent = errorText(error);
        errorNode.hidden = false;
    }
}
