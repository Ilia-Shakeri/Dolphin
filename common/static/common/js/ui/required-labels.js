/**
 * The red asterisk on a required field's label (2.40.33, product owner: «در
 * تمامی ویزاردهای ساخت، برای اینپوت‌های واجب و مهم ستارهٔ قرمز کوچک بگذار»).
 *
 * The UI kit draws it: `.required` on a label adds a small red «*». Which
 * fields are required is already in the markup (`required` on the control),
 * so this reads it there rather than keeping a second list: every label
 * whose control is required gets the class, now and in any form or dialog
 * added later. A label already marked by hand is left as it is.
 */
function markRequired(root) {
    root.querySelectorAll("label[for]").forEach((label) => {
        const control = document.getElementById(label.getAttribute("for"));
        if (!control) return;
        label.classList.toggle("required", control.required || control.hasAttribute("aria-required"));
    });
}

export function setupRequiredLabels() {
    markRequired(document);
    // A control can become required or optional as a wizard changes (a
    // field that applies only to one choice); and dialogs and steps are
    // filled in later. One observer, attribute and subtree, catches both.
    // Lists and the chat redraw often; the pass runs at most once a frame.
    let queued = false;
    const observer = new MutationObserver(() => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => {
            queued = false;
            markRequired(document);
        });
    });
    observer.observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ["required"]});
}
