import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {DOCUMENT_STATUS_TEXT} from "dolphin/core/labels.js";
import {errorText, globalMessage, showError} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {boardCardHeader, letCardDetailsLinkThrough, paintBoardColumns, setupBoardColumnSearch} from "dolphin/ui/boards.js";
import {labelled} from "dolphin/ui/table.js";

/**
 * The same orders `setupOrders`' table shows, grouped into status
 * columns instead — the order-side sibling of `setupLeadBoard` above,
 * built on the same `jKanban` library. Two real differences from the
 * lead board, both driven by `billing.models.Order` actually having a
 * `TRANSITIONS` table where `sales.Lead` has none:
 *
 * - Dropping a card POSTs `/api/v1/orders/<id>/transition/` with
 *   `{to_status}` — `OrderViewSet.transition` ->
 *   `billing.services.transition_order` — the same endpoint and body
 *   `setupOrderDetail`'s own status `<select>` already uses, not a bare
 *   PATCH like the lead board's status field. That function is what
 *   reserves or releases stock and what can silently redirect a
 *   `confirmed` drop to `cancelled` on a stock shortage; this handler
 *   only has to show whatever status the response actually reports.
 * - Each column declares jKanban's own `dragTo` option from
 *   `ORDER_TRANSITIONS`, so an invalid drop (e.g. `fulfilled` back to
 *   `draft`) is refused by jKanban itself — a greyed-out target and an
 *   auto-reverted drop — before any request is sent. This is display
 *   convenience only: `ORDER_TRANSITIONS` drifting out of sync with the
 *   server's own table could only ever narrow the board's menu, never
 *   widen access, because `transition_order` re-validates independently.
 */
export async function setupOrderBoard() {
    const container = document.getElementById("order-board");
    if (!container || typeof jKanban === "undefined") return;
    letCardDetailsLinkThrough(container);
    const loading = document.getElementById("order-board-loading");
    const errorNode = document.getElementById("order-board-error");
    const canManage = container.dataset.canManageOrders === "true";

    // draft/confirmed/fulfilled/cancelled, the exact order
    // billing.models.Order.Status and ORDER_TRANSITIONS both use.
    const STATUSES = Object.keys(ORDER_TRANSITIONS);
    const pageState = {};

    function boardTitle(status, count) {
        const wrap = document.createElement("div");
        wrap.className = "d-flex align-items-center gap-2";
        const text = document.createElement("span");
        text.textContent = labelled(DOCUMENT_STATUS_TEXT, status);
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
     * pattern `setupLeadBoard`'s own `cardContent` uses for the same
     * reason.
     */
    function cardContent(order) {
        const wrap = document.createElement("div");

        wrap.append(boardCardHeader(
            order.customer_name || `درخواست تأمین ${order.number || ""}`.trim(),
            `/orders/${order.id}/`,
        ));

        const number = document.createElement("div");
        number.className = "fs-8 text-gray-600 mb-1";
        number.dir = "ltr";
        number.textContent = order.number || "—";
        wrap.append(number);

        const amount = document.createElement("div");
        amount.className = "fs-8 text-gray-700 fw-semibold mb-1";
        amount.textContent = money(order.total_amount);
        wrap.append(amount);

        if (order.expected_delivery_at) {
            const row = document.createElement("div");
            row.className = "fs-8 text-gray-600 mb-1";
            row.textContent = `تحویل: ${displayDate(order.expected_delivery_at)}`;
            wrap.append(row);
        }

        const creator = order.created_by_display || order.created_by;
        if (creator) {
            const row = document.createElement("div");
            row.className = "fs-8 text-gray-600 mb-1";
            row.textContent = `ثبت‌شده توسط: ${creator}`;
            wrap.append(row);
        }

        return wrap.innerHTML;
    }

    function toItem(order) {
        return {id: String(order.id), title: cardContent(order)};
    }

    function boardElement(status) {
        return container.querySelector(`.kanban-board[data-id="${status}"] .kanban-drag`);
    }

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
            ? "درخواستی با این جست‌وجو در این ستون نیست."
            : "درخواستی در این وضعیت نیست.";
        drag.append(empty);
    }

    function columnUrl(status, page) {
        const term = pageState[status]?.search;
        const search = term ? `&search=${encodeURIComponent(term)}` : "";
        return `/api/v1/orders/?status=${status}&ordering=-created_at&page=${page}${search}`;
    }

    /** The order-side twin of `setupLeadBoard`'s own `reloadColumn` — see
     *  that one for why the column is rebuilt rather than filtered. */
    async function reloadColumn(status, term) {
        const drag = boardElement(status);
        if (!drag) return;
        pageState[status] = {...pageState[status], search: term};
        try {
            const data = await apiRequest(columnUrl(status, 1));
            drag.innerHTML = "";
            data.results.forEach((order) => kanban.addElement(status, toItem(order)));
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

    async function loadMore(status) {
        const state = pageState[status];
        if (!state?.next) return;
        try {
            const data = await apiRequest(state.next);
            data.results.forEach((order) => kanban.addElement(status, toItem(order)));
            state.next = data.next;
            renderLoadMore(status);
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
                apiRequest(`/api/v1/orders/?status=${status}&ordering=-created_at&page=1`),
            ),
        );
        loading.hidden = true;
        container.hidden = false;

        const boards = STATUSES.map((status, index) => {
            const data = pages[index];
            pageState[status] = {next: data.next};
            counts[status] = data.count;
            return {
                id: status,
                title: boardTitle(status, data.count),
                item: data.results.map(toItem),
                // Restricts valid drop targets to ORDER_TRANSITIONS[status]
                // via jKanban's own dragTo option (see the function
                // docstring above) — a terminal status (fulfilled,
                // cancelled) gets an empty array, so every other column
                // refuses a drop from it.
                dragTo: ORDER_TRANSITIONS[status],
            };
        });

        container.dataset.canDrag = String(canManage);
        kanban = new jKanban({
            element: "#order-board",
            // Narrower than the lead board's own 300px: this board always
            // carries four columns (the lead board carries three), and at
            // 300px four of them plus three 0.75rem gutters (1236px) no
            // longer sit comfortably side by side once the sidebar and
            // this card's own padding are subtracted from a typical
            // laptop viewport — the fourth column fell to the next line.
            // Measured directly against this card's own available width
            // at 1440px (≈1040px, the sidebar and card padding already
            // taken out) and against jKanban's own rendered board width —
            // its per-board margin from `gutter` is not the plain value
            // passed in (`jkanban.bundle.js` splits it unevenly between
            // a board's two inline sides rather than applying it once
            // per gap), so the fit was checked against the real
            // `getBoundingClientRect()` of a rendered board, not the
            // arithmetic the option name suggests. 225px keeps four
            // boards plus their real margins inside that width with room
            // held in reserve, and an order card's own content (customer
            // name, status badge, total) still reads on one line at it.
            gutter: "0.5rem",
            widthBoard: "225px",
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
                const orderId = el.dataset.eid;
                const toStatus = target.parentNode.dataset.id;
                const fromStatus = source.parentNode.dataset.id;
                if (toStatus === fromStatus) return;
                try {
                    const updated = await apiRequest(`/api/v1/orders/${orderId}/transition/`, {
                        method: "POST",
                        body: {to_status: toStatus},
                    });
                    // transition_order can silently redirect a shortage-hit
                    // confirm to cancelled instead — the same case
                    // setupOrderDetail's own status select reports; the
                    // board reflects whatever status actually came back
                    // rather than assuming the drop landed where dropped.
                    const landedStatus = updated.status;
                    if (landedStatus !== toStatus) {
                        el.remove();
                        kanban.addElement(landedStatus, toItem(updated));
                        globalMessage("موجودی کافی نبود؛ درخواست تأمین لغو شد.");
                    } else {
                        globalMessage("وضعیت درخواست تأمین به‌روزرسانی شد.", true);
                    }
                    updateBoardCount(fromStatus, -1);
                    updateBoardCount(landedStatus, 1);
                    renderEmptyState(fromStatus);
                    renderEmptyState(landedStatus);
                } catch (error) {
                    source.append(el);
                    renderEmptyState(fromStatus);
                    renderEmptyState(toStatus);
                    showError(error);
                }
            },
        });

        paintBoardColumns(container, STATUSES);

        STATUSES.forEach((status) => {
            // Same fixed-height, hover-revealed scrollbar as the lead
            // board above — see that block's own comment.
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
// Mirrors billing.models.Order.TRANSITIONS. Display only — the server
// refuses a jump that is not in its own table regardless of what is offered
// here, so a drift in this copy narrows the menu, it never widens access.
// The order board's own dragTo restriction (setupOrderBoard) reads this
// same table, so a drop this omits is one jKanban itself already refuses
// before the request is ever sent.
const ORDER_TRANSITIONS = Object.freeze({
    draft: ["confirmed", "cancelled"],
    confirmed: ["fulfilled", "cancelled"],
    fulfilled: [],
    cancelled: [],
});
