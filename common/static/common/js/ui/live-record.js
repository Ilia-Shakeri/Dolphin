/**
 * A record's page redraws in place when the record changes (2.40.41).
 *
 * Roadmap «اولویت ۱.۵»: «صفحه‌های جزئیات هنگام تغییر همان رکورد کل صفحه را
 * دوباره می‌خوانند؛ بروزرسانی تکه‌ای تجربهٔ نرم‌تری می‌دهد». A detail page
 * registers how it reads its record and how it draws it; `shell/live-page.js`
 * asks it to check whenever a change of its kind is announced. The check reads
 * the record through the ordinary API (so permissions and scope apply), and
 * draws only what actually changed — a page whose record did not move is not
 * touched at all.
 *
 * Unsaved edits are never overwritten: once the reader has typed into a form
 * on the page, a change waits behind a notice until they choose to see it
 * (`apply`) or save their own (`settle` then records the saved state).
 */

let registered = null;
let edited = false;

function noteEdit(event) {
    if (!event.isTrusted) return;
    const target = event.target;
    if (!target?.closest?.("form") || target.closest("dialog, [data-dirty-ignore]")) return;
    edited = true;
}
document.addEventListener("input", noteEdit, true);
document.addEventListener("change", noteEdit, true);

/**
 * Register this page's record. `read()` fetches it (any JSON-able value —
 * several requests may be combined); `draw(value)` puts it on the page.
 * Returns `settle(value)`: call it with whatever the page drew itself (the
 * first load, a save's response) so the next check compares against that and
 * the reader's own saved edits stop counting as unsaved.
 */
export function liveRecord({read, draw}) {
    let last = null;
    const settle = (value) => {
        last = JSON.stringify(value);
        edited = false;
    };
    registered = {
        /** «same», «drawn», or «edited» (a change is waiting behind the reader's edits). */
        async check() {
            const value = await read();
            const text = JSON.stringify(value);
            if (text === last) return "same";
            if (edited) return "edited";
            last = text;
            await draw(value);
            return "drawn";
        },
        /** Draw the current record now, discarding the reader's unsaved edits. */
        async apply() {
            const value = await read();
            last = JSON.stringify(value);
            edited = false;
            await draw(value);
        },
    };
    return settle;
}

/** The page's registered record, or null when it has none. */
export function liveRecordFor() {
    return registered;
}
