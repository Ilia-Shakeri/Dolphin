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
    // 2.40.34: the rest of the lists.
    "sales-documents": ["sales_document"],
    products: ["product"],
    "product-categories": ["product"],
    warehouses: ["inventory"],
    stock: ["inventory"],
    "stock-movements": ["inventory"],
    cheques: ["payment"],
    installments: ["invoice", "payment"],
    quotations: ["quotation"],
    users: ["user"],
    "outbound-sms": ["sms"],
    "inbound-sms": ["sms"],
};

/** Every kind a business record announces — what the dashboard, which counts
 * all of them, listens to (2.40.34). */
export const ALL_BUSINESS_KINDS = [
    "customer", "lead", "interaction", "campaign", "order", "invoice", "payment", "sale",
    "after_sales", "inventory", "sales_document", "product", "quotation", "sms", "task",
];

/**
 * Run `handler` when one of `kinds` changes (or the stream says to re-read
 * everything). Returns a function that unsubscribes.
 */
export function onRealtime(kinds, handler, {delay = 400, whenBusy = false} = {}) {
    let timer = null;
    let pending = null;
    const blocked = () => document.hidden || (!whenBusy && document.querySelector("dialog[open]"));
    // A change that arrives while the tab is hidden or a dialog is open is
    // postponed, not forgotten: it runs when the page becomes visible or the
    // dialog closes.
    const flush = () => {
        if (!pending || blocked()) return;
        const detail = pending;
        pending = null;
        handler(detail);
    };
    const listener = (event) => {
        const kind = event.detail?.kind;
        if (kind !== "resync" && !kinds.includes(kind)) return;
        clearTimeout(timer);
        timer = setTimeout(() => {
            pending = event.detail || {};
            flush();
        }, delay);
    };
    const retry = () => setTimeout(flush, 0);
    document.addEventListener("dolphin:realtime", listener);
    document.addEventListener("visibilitychange", retry);
    document.addEventListener("close", retry, true);
    return () => {
        clearTimeout(timer);
        document.removeEventListener("dolphin:realtime", listener);
        document.removeEventListener("visibilitychange", retry);
        document.removeEventListener("close", retry, true);
    };
}
