import {toPersianDigits} from "dolphin/core/digits.js";
import {gregorianToJalali, jalaliMonthLength, jalaliToGregorian, tehranParts} from "dolphin/core/jalali.js";

/**
 * The lead follow-up calendar.
 *
 * FullCalendar draws a Gregorian grid — the theme's own bundled build
 * carries no Jalali locale — so every label a reader actually reads (the
 * day-of-month number, the month/year title) is overwritten with its
 * Jalali equivalent after render. The grid's own navigation stays
 * Gregorian internally; only what it says on screen is not.
 *
 * Events come from `leads_for(user)` through the ordinary `/api/v1/leads/`
 * endpoint, narrowed to the visible range by `follow_up_from`/`follow_up_to`
 * — the same scope and the same rows the leads list page would show for
 * the same reader, just laid out by date instead of in a table.
 */
/**
 * The clock labels both calendars draw, and the fix-up the format options
 * cannot express on their own.
 *
 * The bundle carries no Jalali/Persian locale, so FullCalendar formatted
 * every clock label through its English default: a grid whose day numbers,
 * month title and weekday names were all deliberately localised was still
 * labelling each event `8:50p`, and the week/day hour axis `12am, 1am, …`.
 * The format below settles the shape — 24 hour, the Iranian convention,
 * zero-padded — and the two helpers settle the digits, which no format
 * option covers.
 */
export const CALENDAR_TIME_FORMAT = {hour: "2-digit", minute: "2-digit", hour12: false};

export function persianiseEventTime(info) {
    const node = info.el.querySelector(".fc-event-time");
    if (node) node.textContent = toPersianDigits(node.textContent);
}

/** The week/day view's hour axis, in Persian digits. */
export function persianSlotLabel(arg) {
    return toPersianDigits(arg.text);
}

/**
 * What the week and day views do that the month view does not.
 *
 * The month grid was already right; the two time-grid views were still on
 * FullCalendar's raw defaults and read as a wall of rules (product-owner
 * request 2026-09-19). Three decisions, in the order they matter:
 *
 * - **Whole hours only.** `slotDuration` defaults to thirty minutes, so
 *   every hour carried a second, unlabelled line through it — twenty-four
 *   extra rules down a week view for a product where nothing is ever
 *   scheduled on a half hour: a follow-up is either a bare Jalali day (it
 *   lands on Tehran midnight and is drawn all-day) or a time picked from
 *   an interaction. One slot per hour, labelled once, is the ask.
 * - **A now line.** The one thing a day view is opened for is "where are
 *   we". `nowIndicator` is FullCalendar's own, not a hand-drawn rule.
 * - **Events that do not overlap.** `slotEventOverlap: false` stops two
 *   appointments in the same hour from being drawn one on top of the
 *   other — side by side is how every calendar product draws them.
 *
 * All twenty-four hours stay on screen rather than the card being capped
 * and scrolled to a working-hours window. Both alternatives were tried and
 * rejected for concrete reasons, recorded here so neither is re-attempted:
 * capping the height means setting FullCalendar 5's calendar-level
 * `height` from `datesSet` (it is not a view-level option, so the `views`
 * hash cannot carry it), and the re-render that triggers rebuilds the
 * toolbar title *after* this file has already replaced it with its Jalali
 * equivalent — measured, and it printed «شهریور ۱۴۰۵Sep 19 – 25, 2026».
 * Narrowing to `slotMinTime`/`slotMaxTime` is worse: a follow-up carrying
 * a clock time outside that window would simply not be drawn, and a
 * calendar that silently omits an appointment is not a tidier calendar.
 */
/**
 * The Gregorian span of the Jalali month a given date falls in.
 *
 * FullCalendar's own `dayGridMonth` is a *Gregorian* month, which is why
 * the two calendars in this panel never showed a whole Persian one: a
 * view titled «مهر» actually held the back half of شهریور and the front
 * half of مهر, and the last few days of the month the title named were
 * simply not on screen (product owner, 2026-09-20: «نمای ماهانه باید کل
 * ماه را از ۱ تا ۳۰/۳۱ کامل نشان دهد»).
 *
 * So the range is computed here in Jalali and handed to FullCalendar as
 * an explicit `visibleRange`. `end` is exclusive, the way every
 * FullCalendar range is.
 */
function jalaliMonthRange(date) {
    const parts = tehranParts(date);
    const [year, month] = gregorianToJalali(parts.year, parts.month, parts.day);
    const [startY, startM, startD] = jalaliToGregorian(year, month, 1);
    const length = jalaliMonthLength(year, month);
    const [endY, endM, endD] = jalaliToGregorian(year, month, length);
    return {
        start: new Date(startY, startM - 1, startD),
        // Exclusive: the day after the last one, so the last day is in.
        end: new Date(endY, endM - 1, endD + 1),
    };
}

/** The first day of the Jalali month `delta` months from `date`. */
function shiftJalaliMonth(date, delta) {
    const parts = tehranParts(date);
    const [year, month] = gregorianToJalali(parts.year, parts.month, parts.day);
    let nextYear = year;
    let nextMonth = month + delta;
    while (nextMonth < 1) { nextMonth += 12; nextYear -= 1; }
    while (nextMonth > 12) { nextMonth -= 12; nextYear += 1; }
    const [gy, gm, gd] = jalaliToGregorian(nextYear, nextMonth, 1);
    return new Date(gy, gm - 1, gd);
}

/**
 * Everything both calendars share about showing a Jalali month.
 *
 * One object rather than two copies: the lead follow-up calendar and the
 * after-sales calendar are the same view over different rows, and the
 * month arithmetic above is exactly the kind of thing that drifts when
 * it exists twice.
 *
 * `prev`/`next` are replaced by custom buttons because FullCalendar's own
 * pair steps by its view's duration, and this view has no fixed duration
 * — a Jalali month is 29, 30 or 31 days depending on which one and which
 * year.
 */
export const JALALI_MONTH_VIEW = {
    type: "dayGrid",
    visibleRange: (current) => jalaliMonthRange(current),
};

/**
 * Wire the two custom month buttons onto a calendar instance.
 *
 * Takes a getter, not the instance: these buttons are part of the config
 * the instance is built from, so the instance does not exist yet when
 * this runs. Only the month view uses them — in week and day view
 * FullCalendar's own prev/next step by a fixed duration, which is
 * correct there — so `datesSet` swaps the toolbar between the two sets.
 */
export function jalaliCalendarButtons(getCalendar) {
    const step = (delta) => {
        const calendar = getCalendar();
        if (calendar) calendar.gotoDate(shiftJalaliMonth(calendar.getDate(), delta));
    };
    return {
        // Left goes back and right goes forward, matching the date
        // picker's own header (`openJalaliPicker`) so the two controls
        // in this panel that step through months agree with each other.
        jalaliPrev: {text: "‹", hint: "ماه قبل", click: () => step(-1)},
        jalaliNext: {text: "›", hint: "ماه بعد", click: () => step(1)},
    };
}

export const CALENDAR_TIME_GRID_OPTIONS = {
    slotDuration: "01:00:00",
    slotLabelInterval: "01:00:00",
    nowIndicator: true,
    slotEventOverlap: false,
    dayMaxEvents: true,
};
