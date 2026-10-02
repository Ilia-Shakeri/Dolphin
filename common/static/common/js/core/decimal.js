import {toLatinDigits} from "dolphin/core/digits.js";

/**
 * Decimal-number fields (a tax rate, a percentage discount): numbers only.
 *
 * `type="number"` lets the letter «e», signs and spaces in and gives no say over
 * what a paste brings, so these are text inputs with the numeric keypad
 * (`inputmode="decimal"`) and this rule. Whatever is typed or pasted is
 * rewritten as it lands: Persian and Arabic digits become Latin, the Persian
 * and Arabic decimal separators and «،» / «/» become a point, everything else is
 * dropped, only the first point is kept, and the fraction is cut to
 * `data-decimal-places` (default 2). A value above `data-decimal-max` is marked
 * invalid with a sentence, so the wizard's own validation refuses to advance.
 * The server validates again; this is the first line, not the only one.
 */
export function normalizeDecimal(raw, places = 2) {
    const text = toLatinDigits(String(raw ?? "")).replace(/[٫،,/]/g, ".");
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
    fraction = fraction.slice(0, places);
    return seenPoint ? `${whole}.${fraction}` : whole;
}

function checkRange(input) {
    const max = input.dataset.decimalMax;
    const value = Number(input.value);
    if (max !== undefined && input.value !== "" && value > Number(max)) {
        input.setCustomValidity(`مقدار نمی‌تواند از ${max} بیشتر باشد.`);
    } else {
        input.setCustomValidity("");
    }
}

export function setupDecimalInputs(root = document) {
    root.querySelectorAll("input[data-decimal-input]").forEach((input) => {
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
    });
}
