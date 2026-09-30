/**
 * Show a spinner on whichever button just started work.
 *
 * Every action handler already disables its button while the request is in
 * flight and re-enables it afterwards. Rather than touch each of those, this
 * watches for exactly that: a button that is disabled by the click/submit
 * that started it is marked `aria-busy` (CSS draws the spinner), and the
 * mark is dropped the moment the button is enabled again. A button that was
 * already disabled never receives a click, so permanent disabling is safe.
 */
export function setupBusyButtons() {
    const mark = (button) => { if (button && button.disabled) button.setAttribute("aria-busy", "true"); };
    document.addEventListener("click", (event) => mark(event.target.closest?.("button.btn")));
    document.addEventListener("submit", (event) => {
        event.target.querySelectorAll?.("button[type='submit']").forEach(mark);
    });
    new MutationObserver((records) => {
        records.forEach((record) => { if (!record.target.disabled) record.target.removeAttribute("aria-busy"); });
    }).observe(document.body, {subtree: true, attributes: true, attributeFilter: ["disabled"]});
}
