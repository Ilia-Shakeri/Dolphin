import {toLatinDigits, toPersianDigits} from "dolphin/core/digits.js";

// --- Jalali dates (BIZ-007) ----------------------------------------------
// What the user reads and types is Jalali; what crosses /api/v1/ stays
// Gregorian ISO-8601. The conversion below is the same arithmetic as
// common/jalali.py and is held to the same ICU reference vectors, so the
// two halves of the product can never disagree about a date.
//
// Intl can format Jalali but cannot parse it, and typing is half the job
// here, so both directions are implemented rather than half-borrowed.

const OPERATIONAL_TIME_ZONE = "Asia/Tehran";
const JALALI_EPOCH_UTC = Date.UTC(622, 2, 21); // 1 Farvardin 1
const DAY_MS = 86400000;
const JALALI_MONTH_OFFSETS = [0, 31, 62, 93, 124, 155, 186, 216, 246, 276, 306, 336];
//: Matches `JALALI_MONTHS` in `common/jalali.py` exactly — the one other
//: place this product spells out a Jalali month by name.
export const JALALI_MONTH_NAMES = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
];
//: Indexed like `Date.prototype.getDay()` (0 = Sunday .. 6 = Saturday) —
//: the Gregorian and Jalali calendars share the same seven weekdays, only
//: the month names differ, so this is not Jalali-specific like the array
//: above. Spelled out in full rather than the single-letter abbreviation
//: (ی/د/س/چ/پ/ج/ش) the lead-follow-up calendar used before: several of
//: those letters are one or two dots apart in the Persian script (چ/ج/ح,
//: پ/ب/ت) and read as near-identical at a calendar header's font size.
export const PERSIAN_WEEKDAY_NAMES = [
    "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه",
];

function isJalaliLeap(year) {
    return (((year + 12) % 33) % 4) === 1;
}

function jalaliYearLength(year) {
    return isJalaliLeap(year) ? 366 : 365;
}

export function gregorianToJalali(year, month, day) {
    let days = Math.round((Date.UTC(year, month - 1, day) - JALALI_EPOCH_UTC) / DAY_MS);
    if (days < 0) throw new RangeError("Date precedes the Jalali epoch.");
    let jalaliYear = 1;
    for (;;) {
        const length = jalaliYearLength(jalaliYear);
        if (days < length) break;
        days -= length;
        jalaliYear += 1;
    }
    for (let index = 11; index >= 0; index -= 1) {
        if (days >= JALALI_MONTH_OFFSETS[index]) {
            return [jalaliYear, index + 1, days - JALALI_MONTH_OFFSETS[index] + 1];
        }
    }
    throw new RangeError("Unreachable: month offsets are exhaustive.");
}

export function jalaliToGregorian(year, month, day) {
    let days = 0;
    for (let each = 1; each < year; each += 1) days += jalaliYearLength(each);
    days += JALALI_MONTH_OFFSETS[month - 1] + day - 1;
    const utc = new Date(JALALI_EPOCH_UTC + days * DAY_MS);
    return [utc.getUTCFullYear(), utc.getUTCMonth() + 1, utc.getUTCDate()];
}

export function jalaliMonthLength(year, month) {
    if (month <= 6) return 31;
    if (month <= 11) return 30;
    return isJalaliLeap(year) ? 30 : 29;
}

/** The wall-clock parts of an instant in the operational time zone. */
export function tehranParts(value) {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    const parts = new Intl.DateTimeFormat("en-CA", {
        timeZone: OPERATIONAL_TIME_ZONE,
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hour12: false,
    }).formatToParts(date).reduce((all, part) => {
        if (part.type !== "literal") all[part.type] = part.value;
        return all;
    }, {});
    return {
        year: Number(parts.year),
        month: Number(parts.month),
        day: Number(parts.day),
        hour: Number(parts.hour === "24" ? "0" : parts.hour),
        minute: Number(parts.minute),
    };
}

/** The operational zone's UTC offset in minutes on a given instant. */
function tehranOffsetMinutes(utcMillis) {
    const parts = tehranParts(new Date(utcMillis));
    const asUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute);
    return Math.round((asUtc - utcMillis) / 60000);
}

/** Tehran wall-clock parts -> the exact instant they name. */
function tehranToInstant(year, month, day, hour, minute) {
    const naive = Date.UTC(year, month - 1, day, hour, minute);
    // Two passes settle the offset even across a DST transition.
    let guess = naive - tehranOffsetMinutes(naive) * 60000;
    guess = naive - tehranOffsetMinutes(guess) * 60000;
    return new Date(guess);
}

/** A stored value as `۱۴۰۵/۰۵/۲۵` (date only). */
export function displayDay(value) {
    if (!value) return "—";
    // A bare `YYYY-MM-DD` is a calendar day, not an instant: read it as
    // written rather than shifting it through a time zone.
    const plain = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value));
    if (plain) {
        const [year, month, day] = gregorianToJalali(+plain[1], +plain[2], +plain[3]);
        return toPersianDigits(`${pad4(year)}/${pad2(month)}/${pad2(day)}`);
    }
    const parts = tehranParts(value);
    if (!parts) return value;
    const [year, month, day] = gregorianToJalali(parts.year, parts.month, parts.day);
    return toPersianDigits(`${pad4(year)}/${pad2(month)}/${pad2(day)}`);
}

/** A stored instant as `۱۴۰۵/۰۵/۲۵ ۱۴:۳۰` in Tehran local time. */
export function displayDate(value) {
    if (!value) return "—";
    const parts = tehranParts(value);
    if (!parts) return value;
    const [year, month, day] = gregorianToJalali(parts.year, parts.month, parts.day);
    return toPersianDigits(
        `${pad4(year)}/${pad2(month)}/${pad2(day)} ${pad2(parts.hour)}:${pad2(parts.minute)}`
    );
}

export function pad2(value) { return String(value).padStart(2, "0"); }
export function pad4(value) { return String(value).padStart(4, "0"); }

/** Fill a Jalali date-time input from a stored value. */
export function localDateTimeValue(value) {
    if (!value) return "";
    const shown = displayDate(value);
    return shown === "—" ? "" : shown;
}

/** The same, for a `data-jalali="date"` input: the day without the time. */
function localDateValue(value) {
    const shown = localDateTimeValue(value);
    // `displayDate` renders "۱۴۰۵/۰۵/۲۷ ۰۱:۰۳"; a date input wants the day.
    return shown ? shown.split(" ")[0] : "";
}

/**
 * Read a typed Jalali value.
 *
 * Returns `{date, hour, minute}` or throws with a Persian message, so every
 * caller reports the same thing for the same mistake.
 */
export function parseJalaliInput(text, {requireTime = false} = {}) {
    const raw = toLatinDigits(String(text || "")).trim();
    if (!raw) return null;
    const match = /^(\d{3,4})[/\-.](\d{1,2})[/\-.](\d{1,2})(?:[\sT]+(\d{1,2}):(\d{2}))?$/.exec(raw);
    if (!match) throw new Error("تاریخ باید به شکل ۱۴۰۵/۰۵/۲۵ باشد.");
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    // Catches a Gregorian value typed into a Jalali field: 2026 is a valid
    // Jalali year arithmetically, but it means 2647 CE.
    if (year < 1200 || year > 1700) throw new Error("سال باید یک سال شمسی معتبر باشد (مثلا ۱۴۰۵).");
    if (month < 1 || month > 12) throw new Error("ماه باید بین ۱ تا ۱۲ باشد.");
    if (day < 1 || day > jalaliMonthLength(year, month)) throw new Error("روز در این ماه معتبر نیست.");
    const hour = match[4] === undefined ? (requireTime ? 0 : 0) : Number(match[4]);
    const minute = match[5] === undefined ? 0 : Number(match[5]);
    if (hour > 23 || minute > 59) throw new Error("ساعت معتبر نیست.");
    return {jalali: [year, month, day], hour, minute};
}

// The two converters below return null rather than throwing on a value they
// cannot read. They run on every keystroke (the export link rebuilds live),
// so throwing would break the handler on a half-typed date. The field's own
// blur handler reports the mistake and `setCustomValidity` blocks submit,
// so an unreadable date is still never silently sent.

/** Typed Jalali date-time -> the ISO instant the API stores, or null. */
export function apiDateTime(value) {
    let parsed;
    try { parsed = parseJalaliInput(value); } catch { return null; }
    if (!parsed) return null;
    const [year, month, day] = jalaliToGregorian(...parsed.jalali);
    return tehranToInstant(year, month, day, parsed.hour, parsed.minute).toISOString();
}

/** Typed Jalali date -> the `YYYY-MM-DD` calendar day the API stores, or null. */
export function apiDate(value) {
    let parsed;
    try { parsed = parseJalaliInput(value); } catch { return null; }
    if (!parsed) return null;
    const [year, month, day] = jalaliToGregorian(...parsed.jalali);
    return `${pad4(year)}-${pad2(month)}-${pad2(day)}`;
}

//: Standard Iranian week, شنبه first — the same order the lead and
//: after-sales calendars already render (`setupLeadCalendar`,
//: `setupAfterSalesCalendar`, both driven by FullCalendar's own
//: `firstDay: 6`).
export const JALALI_WEEKDAY_LETTERS = ["ش", "ی", "د", "س", "چ", "پ", "ج"];

/** Gregorian day-of-week (0=Saturday..6=Friday) for a Jalali calendar day. */
export function jalaliWeekday(year, month, day) {
    const [gy, gm, gd] = jalaliToGregorian(year, month, day);
    const sunday0 = new Date(Date.UTC(gy, gm - 1, gd)).getUTCDay(); // 0=Sun..6=Sat
    return (sunday0 + 1) % 7; // 0=Sat..6=Fri
}
