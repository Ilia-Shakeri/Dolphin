import {toLatinDigits, toPersianDigits} from "dolphin/core/digits.js";

/**
 * Decimal-number fields (a tax rate, a percentage discount): numbers only.
 *
 * `type="number"` lets the letter «e», signs and spaces in and gives no say over
 * what a paste brings, so these are text inputs with the numeric keypad
 * (`inputmode="decimal"`) and this rule. Whatever is typed or pasted is
 * rewritten as it lands: Persian and Arabic digits become Latin, the Persian
 * and Arabic decimal separators and «،» / «/» become a point, everything else is
 * dropped, only the first point is kept, and the fraction is cut to
 * `data-decimal-places` (default 2; `0` for a whole number). A value outside
 * `data-decimal-min`/`data-decimal-max` is marked invalid with a sentence, so
 * the wizard's own validation refuses to advance. Since 2.40.14 every number
 * field in the panel is one of these; none is `type="number"` any more.
 * The server validates again; this is the first line, not the only one.
 */
export function normalizeDecimal(raw, places = 2) {
    let text = toLatinDigits(String(raw ?? "")).replace(/٬/g, "").replace(/٫/g, ".");
    // «1,234.5»: when a real point is already there, commas are thousands
    // separators and go; with no point, a comma / «،» / «/» is the decimal mark.
    text = text.includes(".") ? text.replace(/[،,/]/g, "") : text.replace(/[،,/]/g, ".");
    let whole = "";
    let fraction = "";
    let seenPoint = false;
    for (const char of text) {
        if (char >= "0" && char <= "9") {
            if (seenPoint) fraction += char;
            else whole += char;
        } else if (char === "." && !seenPoint) {
            seenPoint = true;
        }
    }
    // A whole-number field (`places` 0) has no point to keep at all.
    if (places <= 0) return whole;
    fraction = fraction.slice(0, places);
    return seenPoint ? `${whole}.${fraction}` : whole;
}

function checkRange(input) {
    const {decimalMin: min, decimalMax: max} = input.dataset;
    const value = Number(input.value);
    if (max !== undefined && input.value !== "" && value > Number(max)) {
        input.setCustomValidity(`مقدار نمی‌تواند از ${toPersianDigits(max)} بیشتر باشد.`);
    } else if (min !== undefined && input.value !== "" && value < Number(min)) {
        input.setCustomValidity(`مقدار نمی‌تواند از ${toPersianDigits(min)} کمتر باشد.`);
    } else {
        input.setCustomValidity("");
    }
}

export function setupDecimalInputs(root = document) {
    root.querySelectorAll("input[data-decimal-input]").forEach((input) => bindDecimalInput(input));
}

/** One field, for a page that builds it after the panel has started. */
export function bindDecimalInput(input) {
    if (input.dataset.decimalBound) return;
    input.dataset.decimalBound = "1";
    const places = Number(input.dataset.decimalPlaces ?? 2);
    input.addEventListener("input", () => {
        const cleaned = normalizeDecimal(input.value, places);
        if (cleaned !== input.value) input.value = cleaned;
        checkRange(input);
    });
    input.addEventListener("blur", () => {
        if (input.value.endsWith(".")) input.value = input.value.slice(0, -1);
        checkRange(input);
    });
}
