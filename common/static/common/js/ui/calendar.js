import {toPersianDigits} from "dolphin/core/digits.js";
import {gregorianToJalali, jalaliMonthLength, jalaliToGregorian, parseJalaliInput, tehranParts} from "dolphin/core/jalali.js";
import {setupJalaliInputs} from "dolphin/ui/jalali-picker.js";

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
export function jalaliMonthRange(date) {
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
export function shiftJalaliMonth(date, delta) {
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

/**
 * Drag an event across months.
 *
 * A month grid shows one Jalali month, so an event could not be dragged to a
 * day outside it. While one is being dragged, holding the pointer at the
 * calendar's left or right edge steps the month, repeating while held. The
 * calendar is right-to-left, so the left edge is the way forward: «ماه بعد»,
 * matching the toolbar arrows. Only the month view does this; week and day
 * views already step by a fixed span with FullCalendar's own controls.
 *
 * Returns the two FullCalendar hooks to spread into the calendar's options.
 */
const EDGE_ZONE_PX = 56;
const EDGE_DWELL_MS = 650;

export function monthEdgeDragHooks(getCalendar, container) {
    let timer = null;
    let side = 0; // -1 left edge, 1 right edge, 0 none

    const stop = () => {
        clearTimeout(timer);
        timer = null;
        side = 0;
    };
    const arm = () => {
        timer = setTimeout(() => {
            const calendar = getCalendar();
            if (!calendar || calendar.view.type !== "jalaliMonth" || !side) return;
            // Left edge → the next month, right edge → the previous one.
            calendar.gotoDate(shiftJalaliMonth(calendar.getDate(), side < 0 ? 1 : -1));
            arm();
        }, EDGE_DWELL_MS);
    };
    const onMove = (event) => {
        const point = event.touches?.[0] || event;
        const box = container.getBoundingClientRect();
        const inside = point.clientY >= box.top && point.clientY <= box.bottom;
        const next = !inside ? 0 : point.clientX <= box.left + EDGE_ZONE_PX ? -1 : point.clientX >= box.right - EDGE_ZONE_PX ? 1 : 0;
        if (next === side) return;
        stop();
        side = next;
        if (side) arm();
    };
    return {
        eventDragStart: () => {
            document.addEventListener("mousemove", onMove);
            document.addEventListener("touchmove", onMove, {passive: true});
        },
        eventDragStop: () => {
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("touchmove", onMove);
            stop();
        },
    };
}

let moveDialogNode = null;

/**
 * Ask for a Jalali date and resolve with a `Date` — the same day-of-month the
 * user typed, at the event's own clock time — or `null` when cancelled.
 *
 * The keyboard-and-touch way to do what dragging does, and the only way to
 * reach a day more than a month away without dragging through each one.
 */
export function promptMoveToDate(current) {
    if (!moveDialogNode) {
        const dialog = document.createElement("dialog");
        dialog.className = "dolphin-confirm";
        dialog.setAttribute("aria-labelledby", "dolphin-move-title");
        dialog.innerHTML = '<h2 id="dolphin-move-title" class="fs-4 fw-bold mb-3">انتقال به تاریخ</h2>'
            + '<label class="form-label fw-semibold" for="dolphin-move-date">تاریخ جدید</label>'
            + '<input class="form-control form-control-solid" id="dolphin-move-date" type="text" data-jalali="date">'
            + '<p class="text-danger fs-8 mt-1 mb-0" data-move-error></p>'
            + '<div class="d-flex justify-content-end gap-3 mt-6">'
            + '<button class="btn btn-light" type="button" data-move-cancel>انصراف</button>'
            + '<button class="btn btn-primary" type="button" data-move-ok>انتقال</button></div>';
        document.body.appendChild(dialog);
        setupJalaliInputs(dialog);
        moveDialogNode = dialog;
    }
    const dialog = moveDialogNode;
    const input = dialog.querySelector("#dolphin-move-date");
    const errorNode = dialog.querySelector("[data-move-error]");
    input.value = "";
    errorNode.textContent = "";
    return new Promise((resolve) => {
        let answer = null;
        const finish = () => {
            dialog.removeEventListener("close", finish);
            dialog.removeEventListener("click", onClick);
            resolve(answer);
        };
        const onClick = (event) => {
            if (event.target.closest("[data-move-cancel]")) { dialog.close(); return; }
            if (!event.target.closest("[data-move-ok]")) return;
            try {
                const parsed = parseJalaliInput(input.value);
                if (!parsed) throw new Error("تاریخ جدید را وارد کنید.");
                const [gy, gm, gd] = jalaliToGregorian(...parsed.jalali);
                const moved = new Date(current);
                moved.setFullYear(gy, gm - 1, gd);
                answer = moved;
                dialog.close();
            } catch (error) {
                errorNode.textContent = error.message;
            }
        };
        dialog.addEventListener("close", finish);
        dialog.addEventListener("click", onClick);
        dialog.showModal();
        input.focus();
    });
}

/**
 * A small «انتقال به تاریخ…» control inside an event chip. A span, not a
 * button: the chip is itself a link, and a button may not sit inside one.
 */
export function addMoveToDateControl(info, onMove) {
    const host = info.el.querySelector(".fc-event-title, .fc-event-main") || info.el;
    const control = document.createElement("span");
    control.className = "calendar-event-move";
    control.setAttribute("role", "button");
    control.tabIndex = 0;
    control.title = "انتقال به تاریخ…";
    control.setAttribute("aria-label", "انتقال به تاریخ…");
    control.textContent = "⇄";
    const open = async (event) => {
        event.preventDefault();
        event.stopPropagation();
        const moved = await promptMoveToDate(info.event.start);
        if (moved) await onMove(moved);
    };
    control.addEventListener("click", open);
    control.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") open(event);
    });
    host.append(control);
}
