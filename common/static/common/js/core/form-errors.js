//: form -> the wizard wrapped around it, so `showError` can turn a server
//: rejection into a summary on the step the reader is actually looking at.
//: A WeakMap rather than a property on the element: nothing has to be
//: cleaned up when a dialog is discarded.
export const wizardsByForm = new WeakMap();

/**
 * A field's own human name, for the summary above.
 *
 * The `<label for>` a sighted reader is already using is the right name —
 * not the API field key (`campaign_or_batch`), which is an internal
 * identifier nobody on this side of the screen has ever seen. Falls back
 * to the key only when a field genuinely has no label (a whole-form error
 * such as `non_field_errors`, or a server key with no input of its own).
 */
function fieldLabelFor(form, name) {
    const field = form.querySelector(`[name="${CSS.escape(name)}"]`);
    const byFor = field?.id ? form.querySelector(`label[for="${CSS.escape(field.id)}"]`) : null;
    const label = byFor || field?.closest("label") || null;
    const text = label?.textContent?.trim();
    if (text) return text;
    return name === "non_field_errors" ? "این فرم" : name;
}

/**
 * Turn a rejected wizard submit into the summary described above.
 *
 * Reads the same `[data-error-for]` slots `showError` has just filled
 * rather than the payload again, so the summary can never list a reason
 * different from the one printed under the field itself.
 */
export function reportWizardErrors(form) {
    const wizard = wizardsByForm.get(form);
    if (!wizard) return;
    const problems = [];
    form.querySelectorAll("[data-error-for]").forEach((slot) => {
        const message = slot.textContent.trim();
        if (!message) return;
        const name = slot.dataset.errorFor;
        problems.push({
            label: fieldLabelFor(form, name),
            message,
            step: wizard.stepOf(form.querySelector(`[name="${CSS.escape(name)}"]`) || slot),
        });
    });
    wizard.summary.show(problems);
}
