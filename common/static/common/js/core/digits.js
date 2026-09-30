const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

export function toPersianDigits(text) {
    return String(text).replace(/[0-9]/g, (digit) => PERSIAN_DIGITS[Number(digit)]);
}

export function toLatinDigits(text) {
    // Persian ۰-۹ and Arabic-Indic ٠-٩ both normalise to Latin.
    return String(text)
        .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06F0))
        .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));
}

/**
 * Group a price field as it is typed, so nobody types separators by hand.
 *
 * Applied to `[data-money-input]`. The field is `type="text"` rather than
 * `type="number"`, because a number input refuses a grouped value outright.
 * `moneyValue` turns it back into digits on submit.
 */
/**
 * Persian and Arabic digits in any numeric field (2.25.1).
 *
 * A `type="number"` input refuses «۱۲۳» outright — the browser drops the
 * keystroke before any script sees a value — so an operator on a Persian
 * keyboard could not type a quantity or a percentage at all. The digit is
 * translated on its way in instead: `beforeinput` still carries the
 * character, and is cancellable for ordinary typing and pasting, so the
 * Latin digit is inserted in its place. `insertText` keeps the field's
 * own undo history and fires the usual `input` event, so nothing that
 * listens to the field has to know this happened.
 *
 * Text fields that take digits (phone, national id, money) accept Persian
 * digits already and are converted on submit; they are covered too, so a
 * number reads the same way everywhere it is typed. The `input` fallback
 * catches what an on-screen keyboard's composition sends uncancellably.
 */
const NUMERIC_FIELD = [
    'input[type="number"]', 'input[type="tel"]',
    'input[inputmode="numeric"]', 'input[inputmode="decimal"]', 'input[inputmode="tel"]',
].join(", ");
const FOREIGN_DIGIT = /[۰-۹٠-٩٫]/;

function latinNumberText(text) {
    // «٫» is the Persian decimal separator.
    return toLatinDigits(text).replace(/٫/g, ".");
}

function insertLatin(field, text) {
    field.focus();
    // `execCommand` is the only way to insert into a number input: it has
    // no selection API, so `setRangeText` throws there.
    if (document.execCommand && document.execCommand("insertText", false, text)) return;
    field.value += text;
    field.dispatchEvent(new Event("input", {bubbles: true}));
}

export function setupLatinDigitInputs() {
    document.addEventListener("beforeinput", (event) => {
        const field = event.target;
        if (!(field instanceof HTMLInputElement) || !field.matches(NUMERIC_FIELD)) return;
        if (typeof event.data !== "string" || !FOREIGN_DIGIT.test(event.data) || !event.cancelable) return;
        event.preventDefault();
        insertLatin(field, latinNumberText(event.data));
    }, true);
    document.addEventListener("paste", (event) => {
        const field = event.target;
        if (!(field instanceof HTMLInputElement) || !field.matches(NUMERIC_FIELD)) return;
        const text = event.clipboardData?.getData("text") || "";
        if (!FOREIGN_DIGIT.test(text)) return;
        event.preventDefault();
        insertLatin(field, latinNumberText(text));
    }, true);
    document.addEventListener("input", (event) => {
        const field = event.target;
        if (!(field instanceof HTMLInputElement) || !field.matches(NUMERIC_FIELD)) return;
        if (field.type === "number" || !FOREIGN_DIGIT.test(field.value)) return;
        const caret = field.selectionStart;
        field.value = latinNumberText(field.value);
        if (caret !== null) field.setSelectionRange(caret, caret);
    }, true);
}
