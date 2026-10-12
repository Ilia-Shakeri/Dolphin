import {lastWriteAt} from "dolphin/core/api.js";
import {liveRecordFor} from "dolphin/ui/live-record.js";
import {onRealtime} from "dolphin/ui/realtime.js";

/**
 * A record's own page follows changes to that record (2.40.34, product owner:
 * «کل پنل باید لایو باشد و اگر تغییراتی اعمال شد در لحظه بدون رفرش اعمال
 * شود»).
 *
 * Since 2.40.41 the page redraws in place (`ui/live-record.js`): it reads its
 * own record again and draws only what changed — no reload, no jump. Most
 * kinds never tell the browser which record changed (`KINDS_WITHOUT_ID` in
 * `common/realtime.py`: they name a person's record), so a page that has
 * registered its record checks on every change of its kind; the check is one
 * read and draws nothing when nothing moved. A page without a registered
 * record keeps the old behaviour: it reloads, scroll kept, when the event
 * names it.
 *
 * Never while the reader is in the middle of something: a field with focus
 * or an open dialog holds it back until they are done; unsaved edits on the
 * page are kept and a notice offers the new version instead; and not for the
 * page's own saves, which already drew their result (`lastWriteAt`).
 */
const DETAIL_KINDS = {
    "after-sales-detail": ["after_sales"],
    "campaign-detail": ["campaign"],
    "interaction-detail": ["interaction"],
    "invoice-detail": ["invoice", "payment"],
    "lead-detail": ["lead"],
    "order-detail": ["order", "invoice"],
    "payment-detail": ["payment", "invoice"],
    "product-category-detail": ["product"],
    "product-detail": ["product"],
    "sale-detail": ["sale"],
    "sales-document-detail": ["sales_document"],
    "warehouse-detail": ["inventory"],
    "person-profile": ["customer", "user", "invoice", "payment", "lead", "interaction", "sale", "task"],
};
const OWN_ECHO_MS = 5000;
const SCROLL_KEY = "dolphin:live-scroll";

function busy() {
    const active = document.activeElement;
    const typing = active && (active.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName));
    return Boolean(typing || document.querySelector("dialog[open]"));
}

/** «This record changed elsewhere» — shown instead of overwriting unsaved edits. */
function showChangedNotice(record) {
    if (document.getElementById("live-record-notice")) return;
    const notice = document.createElement("div");
    notice.id = "live-record-notice";
    notice.className = "live-record-notice";
    notice.setAttribute("role", "status");
    const text = document.createElement("span");
    text.textContent = "این رکورد در جای دیگری تغییر کرد.";
    const show = document.createElement("button");
    show.type = "button";
    show.className = "btn btn-sm btn-primary";
    show.textContent = "نمایش نسخهٔ تازه";
    show.addEventListener("click", async () => {
        notice.remove();
        try { await record.apply(); } catch (error) { /* the next change tries again */ }
    });
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "btn btn-sm btn-icon btn-light";
    dismiss.setAttribute("aria-label", "بستن");
    dismiss.textContent = "×";
    dismiss.addEventListener("click", () => notice.remove());
    notice.append(text, show, dismiss);
    document.body.append(notice);
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
    let checking = false;

    function whenFree(task) {
        if (!busy()) return task();
        if (waiting) return undefined;
        waiting = true;
        const retry = () => {
            if (busy()) return;
            document.removeEventListener("focusout", retry, true);
            document.removeEventListener("close", retry, true);
            waiting = false;
            setTimeout(task, 300);
        };
        document.addEventListener("focusout", retry, true);
        document.addEventListener("close", retry, true);
        return undefined;
    }

    async function redraw() {
        const record = liveRecordFor();
        if (!record || checking) return;
        checking = true;
        try {
            if (await record.check() === "edited") showChangedNotice(record);
        } catch (error) {
            // A failed read is not shown: nobody asked for it, and the next
            // change tries again.
        } finally {
            checking = false;
        }
    }

    function reload() {
        try {
            sessionStorage.setItem(SCROLL_KEY, JSON.stringify({path: window.location.pathname, y: window.scrollY}));
        } catch (error) { /* no storage: the page reopens at its top */ }
        window.location.reload();
    }

    onRealtime(kinds, (detail) => {
        if (Date.now() - lastWriteAt() < OWN_ECHO_MS) return;
        if (liveRecordFor()) {
            // Any change of this page's kinds, or a re-read of everything.
            whenFree(redraw);
            return;
        }
        // No registered record: only this record, and by reloading.
        if (detail.kind === "resync" || String(detail.id) !== id) return;
        whenFree(reload);
    }, {whenBusy: true, delay: 800});
}
