import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {JALALI_MONTH_NAMES, PERSIAN_WEEKDAY_NAMES, displayDate, displayDay, gregorianToJalali, tehranParts} from "dolphin/core/jalali.js";
import {errorText, globalMessage, showError} from "dolphin/core/messages.js";
import {CALENDAR_TIME_FORMAT, CALENDAR_TIME_GRID_OPTIONS, JALALI_MONTH_VIEW, addMoveToDateControl, jalaliCalendarButtons, monthEdgeDragHooks, persianSlotLabel, persianiseEventTime} from "dolphin/ui/calendar.js";
import {chartPalette} from "dolphin/ui/charts.js";
import {loadAllPages} from "dolphin/ui/lists.js";

export async function setupLeadCalendar() {
    const container = document.getElementById("lead-calendar");
    if (!container || typeof FullCalendar === "undefined") return;
    const loading = document.getElementById("lead-calendar-loading");
    const errorNode = document.getElementById("lead-calendar-error");

    function jalaliDayLabel(date) {
        const [, , day] = gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
        return toPersianDigits(String(day));
    }

    function jalaliTitle(date, exact) {
        const [year, month, day] = gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
        const monthYear = `${JALALI_MONTH_NAMES[month - 1]} ${toPersianDigits(String(year))}`;
        // `exact`: the day view has only one date on screen and nothing
        // else naming it, unlike month view (numbered cells) or week view
        // (a date under each column's own header) — so its title is the
        // one place that has to carry the day-of-month too.
        return exact ? `${toPersianDigits(String(day))} ${monthYear}` : monthYear;
    }

    const palette = chartPalette();
    // pending/completed/cancelled — the three backend-owned Lead statuses,
    // same order and same colours `sales_by_agent`-style charts already use
    // for "needs attention" (primary), "done" (success), "closed out, no
    // action" (danger) — and the same three the legend above already shows.
    const STATUS_META = {
        pending: {label: "در انتظار تکمیل", color: palette[0], badgeClass: "badge-light-primary"},
        completed: {label: "تکمیل", color: palette[1], badgeClass: "badge-light-success"},
        cancelled: {label: "کنسل شده", color: palette[4], badgeClass: "badge-light-danger"},
    };

    /**
     * A hover preview richer than one title-attribute line: who it's for,
     * status, agent, source/campaign, and a notes preview — everything a
     * follow-up needs to be actioned without leaving the calendar.
     *
     * Every piece of text below goes through `textContent`, never through
     * an HTML string built by hand — a customer name, note, or source is
     * free text someone typed, and this file never assigns to `innerHTML`
     * from a template literal anywhere. `content.innerHTML` is read once,
     * at the very end, only to hand Bootstrap's Popover the markup it
     * requires — by then every value in it was already escaped by the
     * browser itself when each `textContent` assignment above ran.
     */
    function buildEventPopoverContent(lead, meta, overdue, when) {
        const wrap = document.createElement("div");

        const nameLine = document.createElement("div");
        nameLine.className = "fw-bold fs-6 mb-1";
        nameLine.textContent = lead.customer_name || "سرنخ بدون مشتری";
        wrap.append(nameLine);

        const badgeRow = document.createElement("div");
        badgeRow.className = "d-flex flex-wrap gap-2 mb-2";
        const statusBadge = document.createElement("span");
        statusBadge.className = `badge ${meta.badgeClass}`;
        statusBadge.textContent = meta.label;
        badgeRow.append(statusBadge);
        if (overdue) {
            const overdueBadge = document.createElement("span");
            overdueBadge.className = "badge badge-light-danger";
            overdueBadge.textContent = "دیرکرد";
            badgeRow.append(overdueBadge);
        }
        wrap.append(badgeRow);

        [
            ["کارشناس", lead.assigned_to_display],
            ["منبع", lead.source],
            ["کمپین", lead.campaign_or_batch],
            ["زمان پیگیری", when],
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

        if (lead.notes) {
            const notes = document.createElement("div");
            notes.className = "fs-8 text-gray-600 mt-2 pt-2 border-top border-gray-300";
            notes.textContent = lead.notes.length > 100 ? `${lead.notes.slice(0, 100)}…` : lead.notes;
            wrap.append(notes);
        }
        return wrap;
    }

    async function saveFollowUp(id, start) {
        await apiRequest(`/api/v1/leads/${id}/`, {
            method: "PATCH",
            body: {next_follow_up_at: start.toISOString()},
        });
        globalMessage("تاریخ پیگیری به‌روزرسانی شد.", true);
    }

    // `let`, declared before the config that references it: the two
    // custom month buttons below close over this and only ever run
    // after the assignment has happened.
    let calendar;
    calendar = new FullCalendar.Calendar(container, {
        direction: "rtl",
        height: "auto",
        firstDay: 6, // Saturday — the Iranian week start.
        // Otherwise the trailing/leading days of the *adjacent* Gregorian
        // month fill out the grid's first/last week — and because every
        // cell's own number is re-labelled in Jalali (`dayCellContent`
        // below), those spillover cells show Jalali day numbers that
        // belong to neither the month in the title nor a full week of
        // their own, reading as numbers with no calendar around them
        // (design review, 2026-09-12).
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
            // Month view names the column once, above every date in it —
            // the date itself is each cell's own number (`dayCellContent`
            // below), so the header needs only the name.
            if (arg.view.type === "jalaliMonth") return weekday;
            // Week/day views have one column per date, so the header is
            // the only place that date appears — stacked on two lines,
            // not one, so a wide name like "چهارشنبه" never has to shrink
            // to fit next to a day number in a week view's seven columns.
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
            // The visible grid's own centre, not `currentStart` — a month
            // view's first cell is often still the tail of the previous
            // Jalali month, which would title "شهریور" a grid that reads
            // as "مهر" to anyone looking at it.
            const middle = new Date((info.view.currentStart.getTime() + info.view.currentEnd.getTime()) / 2);
            const titleEl = container.querySelector(".fc-toolbar-title");
            if (titleEl) titleEl.textContent = jalaliTitle(middle, false);
        },
        editable: true,
        eventStartEditable: true,
        eventDurationEditable: false,
        ...CALENDAR_TIME_GRID_OPTIONS,
        // Without this, a timed follow-up (most of them — only a
        // date-only one is all-day) renders in month view as FullCalendar's
        // default small dot + text, and the status colour all but
        // disappears into a single-pixel dot. Block display gives every
        // follow-up the same full-colour chip regardless of view, so
        // status is readable at a glance everywhere, not just in week/day.
        eventDisplay: "block",
        eventTimeFormat: CALENDAR_TIME_FORMAT,
        slotLabelFormat: CALENDAR_TIME_FORMAT,
        slotLabelContent: persianSlotLabel,
        allDayText: "تمام‌روز",
        moreLinkText: (count) => `+${toPersianDigits(String(count))} مورد دیگر`,
        events: async (fetchInfo, successCallback, failureCallback) => {
            try {
                const query = new URLSearchParams({
                    follow_up_from: fetchInfo.startStr,
                    follow_up_to: fetchInfo.endStr,
                });
                const leads = await loadAllPages(`/api/v1/leads/?${query}`);
                loading.hidden = true;
                errorNode.hidden = true;
                container.hidden = false;
                const now = new Date();
                successCallback(leads.map((lead) => {
                    // A follow-up set from the date-only picker lands on
                    // Tehran midnight; that is what "all day" means here —
                    // a time-precise one (set from an interaction's own
                    // datetime field) keeps its clock.
                    const parts = tehranParts(lead.next_follow_up_at);
                    const allDay = Boolean(parts && parts.hour === 0 && parts.minute === 0);
                    const meta = STATUS_META[lead.status] || STATUS_META.pending;
                    // Only a still-pending follow-up can be "late" — a
                    // completed or cancelled one has nothing left to act on,
                    // so a past date on those is expected, not a warning.
                    const overdue = lead.status === "pending" && new Date(lead.next_follow_up_at) < now;
                    return {
                        id: String(lead.id),
                        title: lead.customer_name
                            ? `${lead.customer_name}${lead.assigned_to_display ? " — " + lead.assigned_to_display : ""}`
                            : `سرنخ بدون مشتری${lead.assigned_to_display ? " — " + lead.assigned_to_display : ""}`,
                        start: lead.next_follow_up_at,
                        allDay,
                        backgroundColor: meta.color,
                        borderColor: meta.color,
                        classNames: overdue ? ["fc-event-overdue"] : [],
                        extendedProps: {lead, meta, overdue},
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
            window.location.href = `/leads/${info.event.id}/`;
        },
        ...monthEdgeDragHooks(() => calendar, container),
        eventDrop: async (info) => {
            try {
                await saveFollowUp(info.event.id, info.event.start);
            } catch (error) {
                info.revert();
                showError(error);
            }
        },
        eventDidMount: (info) => {
            persianiseEventTime(info);
            const {lead, meta, overdue} = info.event.extendedProps;
            // FullCalendar's day-limit ("+N more") layout pass mounts an
            // event element to measure it before every event is known to
            // carry the custom props this file attaches — a mount with no
            // `lead` yet is that measurement pass, not a real one, and
            // gets no popover; the later real mount for the same event
            // still gets one normally.
            if (!lead) return;
            addMoveToDateControl(info, async (moved) => {
                try {
                    await saveFollowUp(info.event.id, moved);
                    calendar.refetchEvents();
                } catch (error) {
                    showError(error);
                }
            });
            const when = info.event.allDay
                ? displayDay(info.event.startStr)
                : displayDate(info.event.startStr);
            const content = buildEventPopoverContent(lead, meta, overdue, when);
            // eslint-disable-next-line -- see buildEventPopoverContent's own
            // comment: every value in `content` was already escaped by
            // `textContent` before this line ever runs.
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
