/**
 * The live-update connection (2.38.0).
 *
 * Opens one Server-Sent-Events stream when the page declares it
 * (`<meta name="dolphin-realtime">`, rendered only where the feature is on and
 * the service is configured) and announces each event on the document. If the
 * stream cannot be reached — no service, a proxy that does not route it, a
 * signed-out session — it backs off and, after a few failures, retries slowly:
 * everything keeps working through the timers and refresh-on-focus the
 * panel always had. Nothing depends on this connection existing.
 */
const MAX_FAILURES = 5;
const SLOW_RETRY_MS = 5 * 60 * 1000;

export function setupRealtime() {
    const meta = document.querySelector('meta[name="dolphin-realtime"]');
    if (!meta || typeof window.EventSource === "undefined") return;
    const url = meta.content;
    let source = null;
    let failures = 0;
    let retryTimer = null;

    function announce(data) {
        document.dispatchEvent(new CustomEvent("dolphin:realtime", {detail: {kind: data.k, id: data.i ?? null}}));
    }

    function open() {
        source = new EventSource(url);
        source.onopen = () => { failures = 0; };
        source.onmessage = (message) => {
            try { announce(JSON.parse(message.data)); } catch (error) { /* a malformed event is ignored */ }
        };
        source.onerror = () => {
            // The browser retries a dropped connection by itself; a refused one
            // (404/502/401) it closes, which is where this takes over.
            if (source.readyState !== EventSource.CLOSED) return;
            failures += 1;
            clearTimeout(retryTimer);
            // Backs off with jitter (so a restarted server is not hit by every
            // browser at the same second); after a few failures it keeps trying,
            // slowly, rather than giving up for the life of the page.
            const base = failures >= MAX_FAILURES ? SLOW_RETRY_MS : Math.min(60000, 2000 * 2 ** failures);
            retryTimer = setTimeout(open, base * (0.75 + Math.random() * 0.5));
        };
    }

    open();
    // Catch up at once on returning to the tab: events were not delivered
    // while it was hidden.
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) announce({k: "resync", i: null});
    });
    window.addEventListener("pagehide", () => source?.close());
}
