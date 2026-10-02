/**
 * The one confirmation dialog. It replaces the browser's own `confirm()`,
 * which is grey, blocks the page, ignores the app's font and direction and
 * cannot mark a destructive choice. Resolves true only on the confirm
 * button; Escape, the backdrop and «انصراف» all resolve false.
 */
const DESTRUCTIVE_WORDS = /حذف|باطل|ابطال|لغو|غیرفعال|پایان|آزاد|بسته/;
let confirmDialogNode = null;
export function confirmDialog(message) {
    if (!confirmDialogNode) {
        const dialog = document.createElement("dialog");
        dialog.id = "dolphin-confirm-dialog";
        dialog.className = "dolphin-confirm";
        dialog.setAttribute("aria-labelledby", "dolphin-confirm-title");
        dialog.innerHTML = '<h2 id="dolphin-confirm-title" class="fs-4 fw-bold mb-3">تأیید</h2>'
            + '<p class="dolphin-confirm-text text-gray-700 mb-0"></p>'
            + '<div class="d-flex justify-content-end gap-3 mt-6">'
            + '<button class="btn btn-light" type="button" data-confirm-cancel>انصراف</button>'
            + '<button class="btn btn-primary" type="button" data-confirm-ok>تأیید</button></div>';
        document.body.appendChild(dialog);
        confirmDialogNode = dialog;
    }
    const dialog = confirmDialogNode;
    const text = String(message);
    dialog.querySelector(".dolphin-confirm-text").textContent = text;
    const ok = dialog.querySelector("[data-confirm-ok]");
    const danger = DESTRUCTIVE_WORDS.test(text);
    ok.className = "btn " + (danger ? "btn-danger" : "btn-primary");
    return new Promise((resolve) => {
        let answer = false;
        const cleanup = () => {
            dialog.removeEventListener("close", onClose);
            dialog.removeEventListener("click", onClick);
            resolve(answer);
        };
        const onClose = () => cleanup();
        const onClick = (event) => {
            if (event.target === dialog) { dialog.close(); return; }
            if (event.target.closest("[data-confirm-ok]")) { answer = true; dialog.close(); }
            else if (event.target.closest("[data-confirm-cancel]")) dialog.close();
        };
        dialog.addEventListener("close", onClose);
        dialog.addEventListener("click", onClick);
        dialog.showModal();
        (danger ? dialog.querySelector("[data-confirm-cancel]") : ok).focus();
    });
}

/**
 * Every `<dialog>` in the app (every "ثبت" wizard, every confirm/detail
 * modal) closes when the reader clicks outside it — product-owner
 * decision 2026-09-09. One listener for the whole app rather than one
 * per dialog: a click that lands on the dialog element itself, rather
 * than on anything inside it, is by construction a click on `::backdrop`
 * — `<dialog>` has no visible box beyond its own content, so a listener
 * on `document` whose `event.target` is exactly the open `<dialog>` (not
 * a descendant) is a backdrop click and nothing else. `showModal()`'s
 * own focus trap and Escape-to-close are untouched; this only adds the
 * third way a modal is expected to close.
 */
/**
 * A click on the dim area outside an open dialog closes it — except a wizard.
 *
 * A wizard is a form someone is partway through, and a stray click outside it
 * must never throw their entries away. A wizard closes only from its own close
 * control (which asks first if anything was entered, `ui/wizard.js`).
 */
export function setupDialogBackdropClose() {
    document.addEventListener("click", (event) => {
        const dialog = event.target;
        if (!(dialog instanceof HTMLDialogElement) || !dialog.open) return;
        if (dialog.querySelector(".stepper")) return;
        dialog.close();
    });
}
