import {CURRENCY_LABEL, CURRENCY_UNIT} from "dolphin/core/config.js";
import {toLatinDigits, toPersianDigits} from "dolphin/core/digits.js";

// Group thousands by walking the string rather than going through Number:
// an amount is authoritative as sent, and a float round-trip could move the
// last digit of a large total.
/**
 * A stored amount as the panel shows it: grouped, in rial, no decimals.
 *
 * Rial has no sub-unit in daily use, so a trailing `.00` on every figure is
 * noise that makes an eight-digit total harder to scan, not more precise.
 * The fraction is dropped by rounding half-up on the digit string rather
 * than through `Number`, because the amount is authoritative as stored and
 * a float round-trip could move its last digit.
 *
 * The stored value keeps its two decimals — this is display only.
 */
export function money(value, {withCurrency = true, exact = false} = {}) {
    if (value === null || value === undefined || value === "") return "—";
    const text = String(value).trim();
    const negative = text.startsWith("-");
    let [rawWhole, fraction = ""] = (negative ? text.slice(1) : text).split(".");
    if (!/^\d+$/.test(rawWhole)) return String(value);

    // The reader's own unit, applied before the ceiling below rather
    // than after: rounding the rial up and *then* dividing would report
    // a tenth of a rial more than is owed, the direction the round-up
    // rule exists to avoid. Moving the decimal point one place, never
    // dividing — a rial total can exceed what a double holds exactly,
    // and `common/templatetags/money_tags.py` does the identical string
    // surgery so the screen and the printed document agree digit for
    // digit.
    if (CURRENCY_UNIT === "toman") {
        [rawWhole, fraction] = rawWhole.length > 1
            ? [rawWhole.slice(0, -1), rawWhole.slice(-1) + fraction]
            : ["0", rawWhole + fraction];
    }

    // `exact` is for a value on its way back into an editable field.
    // Rounding there would move the stored amount on the next save, so
    // the fraction the unit conversion produced is kept and printed.
    if (exact) {
        const groupedExact = rawWhole.replace(/\B(?=(\d{3})+(?!\d))/g, "،");
        const trimmed = fraction.replace(/0+$/, "");
        const shownExact = trimmed ? `${groupedExact}.${trimmed}` : groupedExact;
        return toPersianDigits(negative && rawWhole !== "0" ? `‏-${shownExact}` : shownExact);
    }

    // Ceiling, not half-up: any fraction at all rounds the whole number up.
    //
    // The product owner's rule is that the rial figure must never be
    // reported lower than the amount actually owed, and that no decimal is
    // ever shown. Half-up would round 1.4 down to 1 and quietly understate
    // it; rounding up can overstate by at most one rial, which is the
    // direction chosen deliberately.
    //
    // Carried through the digit string with BigInt rather than through a
    // float, because a rial total can exceed what a double represents
    // exactly.
    let whole = rawWhole;
    if (fraction && /[1-9]/.test(fraction)) {
        whole = (BigInt(whole) + 1n).toString();
    }
    const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, "،");
    const body = negative && grouped !== "0" ? `‏-${grouped}` : grouped;
    // Persian digits, same as every date and count elsewhere in the
    // panel — found missing in the 1.7.13 debug sweep, where a rial
    // figure was the one place still reading in Latin numerals next to
    // Jalali dates and Persian-digit counts on the same page. `dir:
    // ltr` on the cell (appendMoneyCell) keeps the digit order left to
    // right regardless of script, so this is display-only: the grouping
    // and rounding above are untouched, and moneyValue() below still
    // reads Persian digits back into what the API expects.
    const shown = withCurrency ? `${body} ${CURRENCY_LABEL}` : body;
    return toPersianDigits(shown);
}

/**
 * Group a plain digit string, without touching its unit.
 *
 * Separate from `moneyDigits` because the two are asked opposite
 * questions. `moneyDigits` converts a *stored* rial amount into what the
 * reader should see; this re-groups what the reader has already typed,
 * which is in their unit already. Running the conversion on every
 * keystroke would divide the field by ten per character.
 */
function groupDigits(text) {
    return toPersianDigits(String(text).replace(/\B(?=(\d{3})+(?!\d))/g, "،"));
}

/**
 * Strip grouping and Persian digits back to a plain digit string.
 *
 * Still in whatever unit the field is displaying — `moneyToStorage`
 * below is what converts. Kept separate because `setupMoneyInputs`
 * re-groups the field as it is typed and must not scale it each time.
 */
function moneyValue(text) {
    const latin = toLatinDigits(String(text || ""));
    return latin.replace(/[،,\s]/g, "").trim();
}

/**
 * A money field's text as the rial digit string the API stores.
 *
 * Every amount in this product is stored in rial; «تومان» is a display
 * unit (see `common/preferences.py`). The multiplication moves the
 * decimal point one place rather than going through `Number`, for the
 * same reason `money()` above divides that way.
 */
export function moneyToStorage(text) {
    const digits = moneyValue(text);
    if (digits === "" || CURRENCY_UNIT !== "toman") return digits;
    const negative = digits.startsWith("-");
    const [whole, fraction = ""] = (negative ? digits.slice(1) : digits).split(".");
    if (!/^\d*$/.test(whole) || !/^\d*$/.test(fraction)) return digits;
    const shifted = `${whole}${fraction.slice(0, 1) || "0"}`.replace(/^0+(?=\d)/, "");
    const rest = fraction.slice(1).replace(/0+$/, "");
    const body = rest ? `${shifted}.${rest}` : shifted;
    return negative ? `-${body}` : body;
}

export function setupMoneyInputs(root = document) {
    root.querySelectorAll("[data-money-input]").forEach((field) => {
        if (field.dataset.moneyBound === "1") return;
        field.dataset.moneyBound = "1";
        field.setAttribute("inputmode", "numeric");
        field.addEventListener("input", () => {
            const raw = moneyValue(field.value);
            const [whole, ...rest] = raw.split(".");
            const digits = whole.replace(/\D/g, "");
            const grouped = digits ? groupDigits(digits) : "";
            // A decimal point that has been typed is kept, and only the
            // whole part is grouped. Dropping the point as it is typed
            // would leave the digits behind it: `15.00` became `1500`,
            // a hundredfold error on a field an operator types by hand.
            // The fraction is dropped on display and at submit instead,
            // where nothing can be mistaken for a further digit.
            field.value = rest.length
                ? `${grouped}.${rest.join("").replace(/\D/g, "")}`
                : grouped;
        });
    });
}

/**
 * A money field's value as digits, or null when it was left empty.
 *
 * Money fields are grouped text, so `Number()` on them would read `1،200`
 * as NaN. The digit string goes to the API as text and is parsed there as
 * a Decimal — turning it into a JS number first would lose precision on
 * large rial amounts.
 */
export function moneyOrNull(value) {
    const digits = moneyToStorage(value);
    return digits === "" ? null : digits;
}

export function textOrNull(value) {
    const text = String(value ?? "").trim();
    return text === "" ? null : text;
}
