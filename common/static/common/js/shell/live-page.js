import {lastWriteAt} from "dolphin/core/api.js";
import {onRealtime} from "dolphin/ui/realtime.js";

/**
 * A record's own page follows changes to that record (2.40.34, product owner:
 * «کل پنل باید لایو باشد و اگر تغییراتی اعمال شد در لحظه بدون رفرش اعمال
 * شود»).
 *
 * When someone else changes the invoice, lead or customer this page shows, the
 * page reads itself again — scroll position kept — rather than showing what it
 * was. Not while the reader is in the middle of something: a field with focus
 * or an open dialog holds it back until they are done; and not for the page's
 * own saves, which already drew their result (`lastWriteAt`). Lists, boards,
 * calendars, charts and the dashboard redraw in place on their own.
 */
const DETAIL_KINDS = {
    "after-sales-detail": ["after_sales"],
    "campaign-detail": ["campaign"],
    "interaction-detail": ["interaction"],
    "invoice-detail": ["invoice"],
    "lead-detail": ["lead"],
    "order-detail": ["order"],
    "payment-detail": ["payment"],
    "product-category-detail": ["product"],
    "product-detail": ["product"],
    "sale-detail": ["sale"],
    "sales-document-detail": ["sales_document"],
    "warehouse-detail": ["inventory"],
    "person-profile": ["customer", "user"],
};
const OWN_ECHO_MS = 5000;
const SCROLL_KEY = "dolphin:live-scroll";

function busy() {
    const active = document.activeElement;
    const typing = active && (active.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName));
    return Boolean(typing || document.querySelector("dialog[open]"));
}

export function setupLivePage() {
    try {
        const saved = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || "null");
        if (saved && saved.path === window.location.pathname) window.scrollTo(0, saved.y);
        sessionStorage.removeItem(SCROLL_KEY);
    } catch (error) { /* storage unavailable: the page simply opens at its top */ }

    const kinds = DETAIL_KINDS[document.body.dataset.page];
    const id = (window.location.pathname.match(/\/(\d+)\/?$/) || [])[1];
    if (!kinds || !id) return;
    let waiting = false;

    function reread() {
        if (busy()) {
            if (waiting) return;
            waiting = true;
            const retry = () => {
                if (busy()) return;
                document.removeEventListener("focusout", retry, true);
                document.removeEventListener("close", retry, true);
                waiting = false;
                setTimeout(reread, 300);
            };
            document.addEventListener("focusout", retry, true);
            document.addEventListener("close", retry, true);
            return;
        }
        try {
            sessionStorage.setItem(SCROLL_KEY, JSON.stringify({path: window.location.pathname, y: window.scrollY}));
        } catch (error) { /* no storage: the page reopens at its top */ }
        window.location.reload();
    }

    onRealtime(kinds, (detail) => {
        // Only this record — a re-read of everything (`resync`) is for lists.
        if (detail.kind === "resync" || String(detail.id) !== id) return;
        if (Date.now() - lastWriteAt() < OWN_ECHO_MS) return;
        reread();
    }, {whenBusy: true, delay: 800});
}
