/**
 * The page-side half of live updates (2.38.0).
 *
 * `shell/realtime.js` owns the connection and announces each event on the
 * document as `dolphin:realtime`; anything that wants to refresh when a kind of
 * record changes subscribes here. An event says only that something of that kind
 * changed — the subscriber reads again through the ordinary API, so permissions
 * and scope apply to what it gets. Subscribers are debounced together, and ask
 * not to be disturbed while someone is typing in a dialog.
 */

/** Which lists refresh on which kinds of change, by the `key` they were built with. */
export const LIVE_KINDS = {
    customers: ["customer"],
    leads: ["lead"],
    interactions: ["interaction"],
    campaigns: ["campaign"],
    "campaign-members": ["campaign"],
    orders: ["order"],
    invoices: ["invoice"],
    payments: ["payment"],
    sales: ["sale"],
    "after-sales": ["after_sales"],
};

/**
 * Run `handler` when one of `kinds` changes (or the stream says to re-read
 * everything). Returns a function that unsubscribes.
 */
export function onRealtime(kinds, handler, {delay = 400, whenBusy = false} = {}) {
    let timer = null;
    const listener = (event) => {
        const kind = event.detail?.kind;
        if (kind !== "resync" && !kinds.includes(kind)) return;
        clearTimeout(timer);
        timer = setTimeout(() => {
            if (document.hidden) return;
            // An open dialog is somebody mid-task; the list under it can wait.
            if (!whenBusy && document.querySelector("dialog[open]")) return;
            handler(event.detail);
        }, delay);
    };
    document.addEventListener("dolphin:realtime", listener);
    return () => {
        clearTimeout(timer);
        document.removeEventListener("dolphin:realtime", listener);
    };
}
