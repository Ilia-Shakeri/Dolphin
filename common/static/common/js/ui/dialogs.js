/**
 * The one confirmation dialog. It replaces the browser's own `confirm()`,
 * which is grey, blocks the page, ignores the app's font and direction and
 * cannot mark a destructive choice. Resolves true only on the confirm
 * button; Escape, the backdrop and «انصراف» all resolve false.
 */
const DESTRUCTIVE_WORDS = /حذف|باطل|ابطال|لغو|غیرفعال|پایان|آزاد|بسته/;
let confirmDialogNode = null;
/** Where the latest pointer press began (see `setupDialogBackdropClose`). */
let pressStartedOn = null;
document.addEventListener("pointerdown", (event) => { pressStartedOn = event.target; }, true);

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
            if (event.target === dialog) { if (pressStartedOn === dialog) dialog.close(); return; }
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
 * Dialogs whose form has been touched since they were opened (2.40.10 — until
 * then only the stepper wizards were guarded). One listener warns before the
 * tab is closed or reloaded while any is open and dirty.
 */
const dirtyDialogs = new Set();
let unloadGuardBound = false;
const UNSAVED_MESSAGE = "تغییرات ذخیره نشده‌اند. آیا مطمئن هستید که می‌خواهید خارج شوید؟";

function bindUnloadGuard() {
    if (unloadGuardBound) return;
    unloadGuardBound = true;
    window.addEventListener("beforeunload", (event) => {
        if (!dirtyDialogs.size) return;
        event.preventDefault();
        event.returnValue = "";
    });
}

/** Whether the reader changed something in this open dialog. */
export function isDialogDirty(dialog) {
    return dirtyDialogs.has(dialog);
}

/**
 * The shared rules for closing a dialog that holds a form, applied once per
 * dialog:
 *
 * - "dirty" means the reader changed a field (a trusted `input`/`change`
 *   event, or one marked `userInitiated`); values the page fills in itself
 *   are not changes, and a control marked `data-dirty-ignore` (a search box
 *   that only narrows a list) never counts;
 * - closing a pristine dialog is immediate;
 * - closing a dirty one — from its × or the backdrop — asks first;
 * - Escape never closes a dirty dialog (it would throw the entries away
 *   without a question) but closes a pristine one.
 *
 * Closing from code, after a successful save, is not intercepted.
 */
export function guardDirtyDialog(dialog, form) {
    if (!(dialog instanceof HTMLDialogElement) || !form || dialog.dataset.dirtyGuard) return;
    dialog.dataset.dirtyGuard = "1";
    bindUnloadGuard();
    const markDirty = (event) => {
        if (event.target?.closest?.("[data-dirty-ignore]")) return;
        if (event.isTrusted || event.userInitiated) dirtyDialogs.add(dialog);
    };
    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);
    new MutationObserver(() => {
        if (dialog.open) dirtyDialogs.delete(dialog);
    }).observe(dialog, {attributes: true, attributeFilter: ["open"]});
    dialog.addEventListener("close", () => dirtyDialogs.delete(dialog));
    dialog.addEventListener("cancel", (event) => {
        if (dirtyDialogs.has(dialog)) event.preventDefault();
    });
    dialog.addEventListener("click", async (event) => {
        if (!event.target.closest?.("[data-close-dialog]") || !dirtyDialogs.has(dialog)) return;
        event.stopPropagation();
        event.preventDefault();
        await closeIfConfirmed(dialog);
    }, true);
}

async function closeIfConfirmed(dialog) {
    if (await confirmDialog(UNSAVED_MESSAGE)) {
        dirtyDialogs.delete(dialog);
        dialog.close();
    }
}

/**
 * A click on the dim area outside an open dialog closes it — except a wizard,
 * and never with unsaved entries.
 *
 * A wizard is a form someone is partway through, and a stray click outside it
 * must never throw their entries away: it closes only from its own close
 * control. Any other dialog with a form closes from the backdrop at once while
 * untouched, and asks first once something was entered (`guardDirtyDialog`,
 * bound here to every such dialog on the page). Only a press that both began
 * and ended on the backdrop counts.
 */
export function setupDialogBackdropClose() {
    document.querySelectorAll("dialog").forEach((dialog) => {
        if (dialog.querySelector(".stepper")) return;
        const form = dialog.querySelector("form");
        if (form) guardDirtyDialog(dialog, form);
    });
    document.addEventListener("click", (event) => {
        const dialog = event.target;
        if (!(dialog instanceof HTMLDialogElement) || !dialog.open) return;
        if (dialog.querySelector(".stepper")) return;
        // Dragging a text selection out of a field and releasing over the dim
        // area is a click on the dialog element too; only a press that also
        // began there counts.
        if (pressStartedOn !== dialog) return;
        if (dirtyDialogs.has(dialog)) {
            closeIfConfirmed(dialog);
            return;
        }
        dialog.close();
    });
}
