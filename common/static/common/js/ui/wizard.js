import {toPersianDigits} from "dolphin/core/digits.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {wizardsByForm} from "dolphin/core/form-errors.js";

/**
 * Wire the theme's own real `DolphinStepper` inside a create dialog's `.stepper`.
 *
 * The vendor component only tracks the current step and toggles its own
 * `current`/`completed`/`pending`/`first`/`between`/`last` classes — the
 * already-loaded theme stylesheet is what shows and hides the previous/
 * next/submit buttons from those. Advancing past "next" is left to the
 * page on purpose (this is how the vendor's own reference wizard is
 * wired too): it is the one place worth gating on the step's own
 * required fields, the same native check the browser would already run
 * on submit if these forms were not marked `novalidate`. No form-
 * validation library or SweetAlert is pulled in for it — neither is used
 * anywhere else in this codebase, and `showError`/`data-error-for`
 * already cover the server's own validation once the form is sent.
 *
 * The submit button stays a plain `type="submit"` inside the form, so
 * the existing `setupDocumentList` submit handler needs no change at
 * all: the wizard only decides which step is visible.
 */
/**
 * Wizards whose form has been touched since they were opened. One listener
 * warns before the tab is closed or reloaded while any is open and dirty.
 */
const dirtyWizards = new Set();
let unloadGuardBound = false;

const UNSAVED_MESSAGE = "تغییرات ذخیره نشده‌اند. آیا مطمئن هستید که می‌خواهید خارج شوید؟";

function bindUnloadGuard() {
    if (unloadGuardBound) return;
    unloadGuardBound = true;
    window.addEventListener("beforeunload", (event) => {
        if (!dirtyWizards.size) return;
        event.preventDefault();
        event.returnValue = "";
    });
}

/**
 * The shared rules for closing a wizard, applied to every one of them here
 * rather than page by page:
 *
 * - "dirty" means the reader changed a field (a trusted `input`/`change`
 *   event). Values the page fills in itself are not changes.
 * - closing a pristine wizard is immediate;
 * - closing a dirty one from its close control asks first;
 * - Escape never closes a dirty wizard (it would throw the entries away
 *   without a question) but closes a pristine one;
 * - the backdrop never closes a wizard at all (`setupDialogBackdropClose`).
 *
 * Closing from code, after a successful save, is not intercepted.
 */
function guardWizardClosing(dialog, form) {
    if (!(dialog instanceof HTMLDialogElement) || !form) return;
    bindUnloadGuard();
    const markDirty = (event) => {
        if (event.isTrusted) dirtyWizards.add(dialog);
    };
    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);
    new MutationObserver(() => {
        if (dialog.open) dirtyWizards.delete(dialog);
    }).observe(dialog, {attributes: true, attributeFilter: ["open"]});
    dialog.addEventListener("close", () => dirtyWizards.delete(dialog));
    dialog.addEventListener("cancel", (event) => {
        if (dirtyWizards.has(dialog)) event.preventDefault();
    });
    dialog.addEventListener("click", async (event) => {
        if (!event.target.closest?.("[data-close-dialog]") || !dirtyWizards.has(dialog)) return;
        event.stopPropagation();
        event.preventDefault();
        if (await confirmDialog(UNSAVED_MESSAGE)) {
            dirtyWizards.delete(dialog);
            dialog.close();
        }
    }, true);
}

export function setupWizard(dialog, {onReachLastStep, validateStep} = {}) {
    const root = dialog?.querySelector(".stepper");
    if (!root) return null;
    const stepper = new DolphinStepper(root);
    const form = root.querySelector("form");
    guardWizardClosing(dialog, form);
    const navs = [...root.querySelectorAll('[data-dolphin-stepper-element="nav"]')];
    const contents = [...root.querySelectorAll('[data-dolphin-stepper-element="content"]')];
    const totalSteps = navs.length;
    const contentOf = (index) => contents[index - 1];

    /** The step a field lives on, 1-based; 0 if it is on none of them. */
    function stepOf(node) {
        const content = node?.closest('[data-dolphin-stepper-element="content"]');
        return content ? contents.indexOf(content) + 1 : 0;
    }

    function stepTitle(index) {
        return navs[index - 1]?.querySelector(".stepper-title")?.textContent?.trim() || "";
    }

    const summary = form ? createWizardErrorSummary(root, contents, stepTitle, (index) => {
        stepper.goTo(index);
        dialog.scrollTop = 0;
    }) : null;
    if (form && summary) wizardsByForm.set(form, {stepOf, stepTitle, summary});

    stepper.on("dolphin.stepper.next", () => {
        const current = stepper.getCurrentStepIndex();
        const invalid = contentOf(current)?.querySelector(":invalid");
        if (invalid) {
            // Both, not one: the browser's own bubble says what is wrong
            // right where the cursor is about to land, and the sentence
            // written into this field's own `[data-error-for]` slot stays
            // on screen after the bubble fades — which is the half that
            // used to be missing, so a person who looked away came back
            // to a step that refused to advance and said nothing about
            // why (product-owner request 2026-09-19).
            writeNativeValidationMessage(invalid);
            invalid.reportValidity();
            invalid.focus?.();
            return;
        }
        // Everything the markup itself cannot say: a product chosen on
        // two rows, more rows than the server will accept. `validateStep`
        // returns a sentence to refuse with, or nothing to allow.
        const complaint = validateStep?.(current, contentOf(current));
        if (complaint) {
            const slot = contentOf(current)?.querySelector("[data-step-error]");
            if (slot) {
                slot.textContent = complaint;
                slot.hidden = false;
                slot.scrollIntoView({block: "nearest"});
            }
            return;
        }
        contentOf(current)?.querySelectorAll("[data-step-error]").forEach((slot) => {
            slot.textContent = "";
            slot.hidden = true;
        });
        stepper.goNext();
        dialog.scrollTop = 0;
        if (stepper.getCurrentStepIndex() === totalSteps) onReachLastStep?.();
    });
    stepper.on("dolphin.stepper.previous", () => {
        stepper.goPrevious();
        dialog.scrollTop = 0;
    });
    return stepper;
}

/**
 * Put the browser's own validation sentence into the field's own error
 * slot, so it survives the bubble.
 *
 * `validationMessage` is the browser's localised text, not one written
 * here — which is the point: it already says *which* constraint failed
 * ("لطفاً این فیلد را پر کنید", "مقدار باید بزرگ‌تر از ۰ باشد"), and
 * re-wording it here would be a second, drifting copy of a rule the
 * browser already enforces from the markup.
 */
function writeNativeValidationMessage(field) {
    const slot = field.form?.querySelector(`[data-error-for="${field.name}"]`);
    if (slot && field.validationMessage) slot.textContent = field.validationMessage;
}

/**
 * The panel that explains a rejected submit *on the review step*.
 *
 * The defect this exists for: every wizard ends on "بازبینی و ثبت", and
 * submitting from there sends the whole form. When the server rejects a
 * field, `showError` writes the reason into that field's own
 * `[data-error-for]` paragraph — which sits on step 1 or step 2, hidden
 * behind the review step the reader is standing on. All they saw was the
 * generic red banner, with no way to tell which field, or even which
 * step, was the problem (product-owner request 2026-09-19).
 *
 * So this collects the same field errors, names each field by its own
 * `<label>`, says which numbered step it is on, and offers a button that
 * jumps straight there. Built in JavaScript rather than added to fifteen
 * templates: the markup would be identical in every one of them, and a
 * wizard added later would silently not have it.
 */
function createWizardErrorSummary(root, contents, stepTitle, goToStep) {
    const last = contents[contents.length - 1];
    if (!last) return null;
    const panel = document.createElement("div");
    panel.className = "wizard-review-errors";
    panel.setAttribute("role", "alert");
    panel.hidden = true;
    const heading = document.createElement("p");
    heading.className = "wizard-review-errors-title";
    heading.textContent = "این موارد باید اصلاح شوند:";
    const list = document.createElement("ul");
    list.className = "wizard-review-errors-list";
    panel.append(heading, list);
    // Under the step's own heading («بازبینی مشتری» and the rest), not
    // above it: a heading names the screen, and an alert that jumped in
    // front of it read as though something had gone wrong with the page
    // rather than with the form on it. Every one of the fifteen wizards
    // opens its review step with that `h3`; `prepend` is the fallback for
    // one that some day does not.
    const stepHeading = last.querySelector("h3");
    if (stepHeading) stepHeading.after(panel); else last.prepend(panel);

    return {
        clear() {
            list.replaceChildren();
            panel.hidden = true;
        },
        /** `problems` is `[{label, message, step}]`, already resolved. */
        show(problems) {
            list.replaceChildren();
            problems.forEach(({label, message, step}) => {
                const item = document.createElement("li");
                const name = document.createElement("span");
                name.className = "wizard-review-errors-field";
                name.textContent = label;
                const reason = document.createElement("span");
                reason.className = "wizard-review-errors-reason";
                reason.textContent = message;
                item.append(name, reason);
                if (step) {
                    const jump = document.createElement("button");
                    jump.type = "button";
                    jump.className = "btn btn-sm btn-light-primary wizard-review-errors-jump";
                    const title = stepTitle(step);
                    jump.textContent = title
                        ? `مرحلهٔ ${toPersianDigits(String(step))} — ${title}`
                        : `مرحلهٔ ${toPersianDigits(String(step))}`;
                    jump.addEventListener("click", () => goToStep(step));
                    item.append(jump);
                }
                list.append(item);
            });
            panel.hidden = !problems.length;
            if (problems.length) root.scrollIntoView({block: "nearest"});
        },
    };
}

/** A field's chosen option text for a review step, or an em dash for one
 * nothing has been picked for yet. */
export function selectedOptionText(select) {
    return select?.selectedOptions[0]?.textContent || "—";
}

/**
 * Fill a wizard's review step from `[label, value]` pairs. Read at the
 * moment the step is shown, never kept live — the review step's only job
 * is to reflect what is about to be sent, not to recompute it.
 *
 * One field per line, label on the reading edge and value on the far one,
 * separated by a hairline rule (product-owner request 2026-09-19: the
 * step read as "زشت و درهم"). It used to be a two-column `row g-3` of
 * `col-md-6` cells, each stacking its own label above its own value —
 * which meant the eye had to find four different left edges to read six
 * fields, and a long Persian value in one cell pushed its neighbour's
 * baseline out of line with it. A single column has one edge for every
 * label and one for every value, so the whole step is scanned in one
 * pass; it is also the shape the purchased theme's own invoice/summary
 * blocks use (`d-flex flex-stack` over `separator separator-dashed`),
 * rather than a layout invented here.
 */
export function renderWizardReview(container, rows) {
    if (!container) return;
    container.replaceChildren();
    rows.forEach(([label, value]) => {
        const line = document.createElement("div");
        line.className = "wizard-review-row";
        const labelEl = document.createElement("span");
        labelEl.className = "wizard-review-label";
        labelEl.textContent = label;
        const valueEl = document.createElement("span");
        valueEl.className = "wizard-review-value";
        // An empty optional field reads as an em dash, never as a label
        // with nothing beside it. Most callers already write `|| "—"` by
        // hand; doing it here as well means the twelve that did not — an
        // audit of every wizard found them, 2026-09-19 — are covered too,
        // and a wizard written later cannot reintroduce the gap.
        valueEl.textContent = String(value ?? "").trim() || "—";
        line.append(labelEl, valueEl);
        container.append(line);
    });
}
