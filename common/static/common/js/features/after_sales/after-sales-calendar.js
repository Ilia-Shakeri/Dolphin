import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {JALALI_MONTH_NAMES, PERSIAN_WEEKDAY_NAMES, displayDate, displayDay, gregorianToJalali, tehranParts} from "dolphin/core/jalali.js";
import {errorText, globalMessage, showError} from "dolphin/core/messages.js";
import {CALENDAR_TIME_FORMAT, CALENDAR_TIME_GRID_OPTIONS, JALALI_MONTH_VIEW, jalaliCalendarButtons, persianSlotLabel, persianiseEventTime} from "dolphin/ui/calendar.js";
import {chartPalette} from "dolphin/ui/charts.js";
import {loadAllPages} from "dolphin/ui/lists.js";

/**
 * The after-sales side of the follow-up calendar
 * (DOLPHIN_FEATURE_MAP_AND_ROADMAP.md §7 phase E) — the same FullCalendar
 * setup as `setupLeadCalendar` above, adapted for two real differences:
 *
 * - after-sales `status` is free text an elevated role or the assigned
 *   technician types (`transition_after_sales_status`), not a fixed
 *   three-value enum like Lead's — so colour here comes from open/closed
 *   (`closed_at`), the one status fact every deployment shares, not from
 *   the status string itself.
 * - dragging an event PATCHes a plain field on `setupLeadCalendar`
 *   because `next_follow_up_at` is a directly writable Lead field; here
 *   it POSTs to `schedule-appointment` instead, because scheduling an
 *   after-sales appointment carries its own rules (elevated role or the
 *   assigned technician only, refused on a closed case) that a bare
 *   PATCH would bypass — `next_appointment_at` is deliberately read-only
 *   on `AfterSalesRequestSerializer` for exactly that reason.
 */
export async function setupAfterSalesCalendar() {
    const container = document.getElementById("after-sales-calendar");
    if (!container || typeof FullCalendar === "undefined") return;
    const loading = document.getElementById("after-sales-calendar-loading");
    const errorNode = document.getElementById("after-sales-calendar-error");

    function jalaliDayLabel(date) {
        const [, , day] = gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
        return toPersianDigits(String(day));
    }

    function jalaliTitle(date, exact) {
        const [year, month, day] = gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
        const monthYear = `${JALALI_MONTH_NAMES[month - 1]} ${toPersianDigits(String(year))}`;
        return exact ? `${toPersianDigits(String(day))} ${monthYear}` : monthYear;
    }

    const palette = chartPalette();
    const OPEN_COLOR = palette[0];
    const CLOSED_COLOR = palette[1];

    function buildEventPopoverContent(item, overdue, when) {
        const wrap = document.createElement("div");

        const nameLine = document.createElement("div");
        nameLine.className = "fw-bold fs-6 mb-1";
        nameLine.textContent = item.subject || item.customer_name || "پروندهٔ بدون موضوع";
        wrap.append(nameLine);

        const badgeRow = document.createElement("div");
        badgeRow.className = "d-flex flex-wrap gap-2 mb-2";
        const statusBadge = document.createElement("span");
        statusBadge.className = `badge ${item.closed_at ? "badge-light-success" : "badge-light-primary"}`;
        statusBadge.textContent = item.status || (item.closed_at ? "بسته" : "باز");
        badgeRow.append(statusBadge);
        if (overdue) {
            const overdueBadge = document.createElement("span");
            overdueBadge.className = "badge badge-light-danger";
            overdueBadge.textContent = "دیرکرد";
            badgeRow.append(overdueBadge);
        }
        wrap.append(badgeRow);

        [
            ["مشتری", item.customer_name],
            ["کارشناس", item.assigned_to_display],
            ["زمان قرار", when],
        ].forEach(([label, value]) => {
            if (!value) return;
            const row = document.createElement("div");
            row.className = "fs-8 text-gray-600 mb-1";
            const strong = document.createElement("span");
            strong.className = "text-gray-800 fw-semibold";
            strong.textContent = `${label}: `;
            row.append(strong, document.createTextNode(value));
            wrap.append(row);
        });

        if (item.description) {
            const description = document.createElement("div");
            description.className = "fs-8 text-gray-600 mt-2 pt-2 border-top border-gray-300";
            description.textContent = item.description.length > 100 ? `${item.description.slice(0, 100)}…` : item.description;
            wrap.append(description);
        }
        return wrap;
    }

    // `let`, declared before the config that references it: the two
    // custom month buttons below close over this and only ever run
    // after the assignment has happened.
    let calendar;
    calendar = new FullCalendar.Calendar(container, {
        direction: "rtl",
        height: "auto",
        firstDay: 6,
        // See the lead calendar's own copy of this option for the full
        // reasoning — same fix, same symptom, same cause.
        showNonCurrentDates: false,
        // `jalaliMonth`, not FullCalendar's own `dayGridMonth`: that one
        // is a *Gregorian* month, so a grid titled «مهر» held half of
        // شهریور and stopped before مهر ended. See `jalaliMonthRange`.
        initialView: "jalaliMonth",
        views: {jalaliMonth: {...JALALI_MONTH_VIEW, buttonText: "ماه"}},
        customButtons: jalaliCalendarButtons(() => calendar),
        // Two prev/next pairs, swapped by `datesSet` below: the custom
        // one steps a whole Jalali month, FullCalendar's own steps the
        // fixed week/day the other views are made of.
        headerToolbar: {start: "jalaliNext,jalaliPrev,next,prev today", center: "title", end: "jalaliMonth,timeGridWeek,timeGridDay"},
        buttonText: {today: "امروز", week: "هفته", day: "روز"},
        dayHeaderContent: (arg) => {
            const weekday = PERSIAN_WEEKDAY_NAMES[arg.date.getDay()];
            if (arg.view.type === "jalaliMonth") return weekday;
            const wrap = document.createElement("div");
            const nameLine = document.createElement("div");
            nameLine.textContent = weekday;
            // Small and muted, not the big bold number it used to be.
            // The instruction for these two views was «فقط ردیف نام
            // روزها باقی بماند» — the row is the day *names*; the date
            // stays because a week view with no dates at all cannot be
            // read, but it stops competing with the name for the row.
            const dayLine = document.createElement("div");
            dayLine.className = "fs-8 fw-semibold text-muted";
            dayLine.textContent = jalaliDayLabel(arg.date);
            wrap.append(nameLine, dayLine);
            return {domNodes: [wrap]};
        },
        // Numbers in the cells belong to the month view alone. In week
        // and day view each column already carries its own date in the
        // header, so a number repeated inside every hour cell was the
        // same date written eight more times (product owner,
        // 2026-09-20: «اعداد داخل خانه‌ها حذف شوند»).
        dayCellContent: (arg) => (
            arg.view.type === "jalaliMonth" ? jalaliDayLabel(arg.date) : ""
        ),
        datesSet: (info) => {
            // The custom month buttons are meaningless in week/day view
            // and FullCalendar's own are wrong in the month view, so the
            // toolbar shows whichever pair fits the view on screen.
            const monthView = info.view.type === "jalaliMonth";
            container.querySelectorAll(".fc-jalaliPrev-button, .fc-jalaliNext-button")
                .forEach((button) => { button.hidden = !monthView; });
            container.querySelectorAll(".fc-prev-button, .fc-next-button")
                .forEach((button) => { button.hidden = monthView; });
            if (info.view.type === "timeGridDay") {
                const titleEl = container.querySelector(".fc-toolbar-title");
                if (titleEl) titleEl.textContent = jalaliTitle(info.view.currentStart, true);
                return;
            }
            const middle = new Date((info.view.currentStart.getTime() + info.view.currentEnd.getTime()) / 2);
            const titleEl = container.querySelector(".fc-toolbar-title");
            if (titleEl) titleEl.textContent = jalaliTitle(middle, false);
        },
        editable: true,
        eventStartEditable: true,
        eventDurationEditable: false,
        ...CALENDAR_TIME_GRID_OPTIONS,
        eventDisplay: "block",
        eventTimeFormat: CALENDAR_TIME_FORMAT,
        slotLabelFormat: CALENDAR_TIME_FORMAT,
        slotLabelContent: persianSlotLabel,
        allDayText: "تمام‌روز",
        moreLinkText: (count) => `+${toPersianDigits(String(count))} مورد دیگر`,
        events: async (fetchInfo, successCallback, failureCallback) => {
            try {
                const query = new URLSearchParams({
                    appointment_from: fetchInfo.startStr,
                    appointment_to: fetchInfo.endStr,
                });
                const items = await loadAllPages(`/api/v1/after-sales/?${query}`);
                loading.hidden = true;
                errorNode.hidden = true;
                container.hidden = false;
                const now = new Date();
                successCallback(items.map((item) => {
                    const parts = tehranParts(item.next_appointment_at);
                    const allDay = Boolean(parts && parts.hour === 0 && parts.minute === 0);
                    // Only a still-open case can be "late" — a closed one
                    // has nothing left to act on, so a past appointment on
                    // one is expected, not a warning.
                    const overdue = !item.closed_at && new Date(item.next_appointment_at) < now;
                    return {
                        id: String(item.id),
                        title: item.customer_name
                            ? `${item.customer_name}${item.assigned_to_display ? " — " + item.assigned_to_display : ""}`
                            : item.subject,
                        start: item.next_appointment_at,
                        allDay,
                        backgroundColor: item.closed_at ? CLOSED_COLOR : OPEN_COLOR,
                        borderColor: item.closed_at ? CLOSED_COLOR : OPEN_COLOR,
                        classNames: overdue ? ["fc-event-overdue"] : [],
                        extendedProps: {item, overdue},
                    };
                }));
            } catch (error) {
                loading.hidden = true;
                errorNode.textContent = errorText(error);
                errorNode.hidden = false;
                failureCallback(error);
            }
        },
        eventClick: (info) => {
            window.location.href = `/after-sales/${info.event.id}/`;
        },
        eventDrop: async (info) => {
            try {
                await apiRequest(`/api/v1/after-sales/${info.event.id}/schedule-appointment/`, {
                    method: "POST",
                    body: {appointment_at: info.event.start.toISOString()},
                });
                globalMessage("زمان قرار به‌روزرسانی شد.", true);
            } catch (error) {
                info.revert();
                showError(error);
            }
        },
        eventDidMount: (info) => {
            persianiseEventTime(info);
            const {item, overdue} = info.event.extendedProps;
            if (!item) return;
            const when = info.event.allDay
                ? displayDay(info.event.startStr)
                : displayDate(info.event.startStr);
            const content = buildEventPopoverContent(item, overdue, when);
            // eslint-disable-next-line -- see buildEventPopoverContent's own
            // comment on setupLeadCalendar: every value here was already
            // escaped by textContent before this line ever runs.
            new bootstrap.Popover(info.el, {
                trigger: "hover focus",
                placement: "top",
                html: true,
                customClass: "lead-calendar-popover",
                content: content.innerHTML,
            });
        },
        eventWillUnmount: (info) => {
            bootstrap.Popover.getInstance(info.el)?.dispose();
        },
    });
    calendar.render();
}
