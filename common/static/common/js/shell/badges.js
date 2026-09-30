import {apiRequest} from "dolphin/core/api.js";

//: The last count each header badge showed, kept for this tab so a new page
//: paints the badge in its first frame instead of after a round trip. Cleared
//: on logout together with the chat cache (`clearChatCache`).
export const BADGE_CACHE_PREFIX = "dolphin.badge.";

/**
 * Keep a header badge truthful without taxing page loads.
 *
 * The badge is painted at once from the tab's last known count; the first
 * real fetch waits for an idle moment (so it never competes with the page's
 * own requests); a hidden tab makes no requests at all; and a tab that
 * becomes visible again refreshes only if the last check is older than one
 * interval.
 */
export function keepBadgeFresh({url, intervalMs, key, apply}) {
    const storageKey = BADGE_CACHE_PREFIX + key;
    try {
        const cached = sessionStorage.getItem(storageKey);
        if (cached !== null) apply(Number(cached));
    } catch (error) {
        // Storage refused (private mode): the first fetch paints the badge.
    }
    let lastRun = 0;
    async function tick() {
        if (document.hidden) return;
        lastRun = Date.now();
        try {
            const data = await apiRequest(url);
            apply(data.count);
            try { sessionStorage.setItem(storageKey, String(data.count)); } catch (error) { /* see above */ }
        } catch (error) {
            // A missed poll tick is not worth bothering anyone about.
        }
    }
    if (window.requestIdleCallback) window.requestIdleCallback(tick, {timeout: 1500});
    else window.setTimeout(tick, 300);
    setInterval(tick, intervalMs);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && Date.now() - lastRun > intervalMs) tick();
    });
}
