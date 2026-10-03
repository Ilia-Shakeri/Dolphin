import {toLatinDigits, toPersianDigits} from "dolphin/core/digits.js";
import {JALALI_MONTH_NAMES, JALALI_WEEKDAY_LETTERS, gregorianToJalali, jalaliMonthLength, jalaliWeekday, pad2, pad4, parseJalaliInput, tehranParts} from "dolphin/core/jalali.js";

let closeOpenJalaliPicker = null; // the open picker's own teardown, or null
import {dispatchUserEvent} from "dolphin/core/events.js";
let openJalaliPickerField = null; // which field it belongs to

/**
 * The one date picker this product has.
 *
 * Every `input[data-jalali]` in the panel opens this and nothing else —
 * filters, wizards, reminders, follow-ups, the report ranges. There is
 * deliberately no second implementation anywhere: a picker is the kind
 * of component that grows a variant per page if you let it, and then
 * each variant gets its own RTL bug.
 *
 * Jalali is computed here rather than delegated: no dependency in this
 * project speaks it (`gregorianToJalali`, `jalaliWeekday`,
 * `jalaliMonthLength` — the same functions every `apiDate`/`apiDateTime`
 * call already runs through), so the grid is drawn from those.
 *
 * The popup's shell is the theme's own: `.menu.menu-sub
 * .menu-sub-dropdown`, exactly what `#user-menu` and
 * `setupListFilterPopovers()` use, so it inherits the light/dark
 * background, shadow, radius and fade-in for free. Only the grids
 * themselves are custom CSS (`.jalali-picker-*` in dolphin.css), because
 * the purchased theme has no Jalali calendar to adapt.
 *
 * Three views, not one (product owner, 2026-09-20): days, then the
 * twelve months of the year, then a decade of years. Each is reached by
 * clicking the part of the title that names it, which is the same
 * gesture every other calendar UI uses, and each returns to the one
 * below it on selection.
 *
 * Typing the date directly keeps working exactly as it always did
 * (`parseJalaliInput` on blur) — this is a second way to fill the same
 * field, never a replacement for the first.
 */
function openJalaliPicker(field) {
    if (openJalaliPickerField === field) return;
    if (closeOpenJalaliPicker) closeOpenJalaliPicker();

    const wantsTime = field.dataset.jalali === "datetime";
    let parsed;
    try { parsed = parseJalaliInput(field.value, {requireTime: wantsTime}); } catch { parsed = null; }
    const nowParts = tehranParts(new Date());
    const [todayYear, todayMonth, todayDay] = gregorianToJalali(nowParts.year, nowParts.month, nowParts.day);

    let viewYear = parsed ? parsed.jalali[0] : todayYear;
    let viewMonth = parsed ? parsed.jalali[1] : todayMonth;
    let selected = parsed ? {year: parsed.jalali[0], month: parsed.jalali[1], day: parsed.jalali[2]} : null;
    let hour = parsed ? parsed.hour : nowParts.hour;
    let minute = parsed ? parsed.minute : nowParts.minute;
    //: "days" | "months" | "years"
    let view = "days";

    const panel = document.createElement("div");
    panel.className = "menu menu-sub menu-sub-dropdown menu-column jalali-picker";
    panel.dir = "rtl";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", wantsTime ? "انتخاب تاریخ و زمان" : "انتخاب تاریخ");

    function navButton(glyph, label) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-icon btn-sm btn-color-muted btn-active-color-primary";
        button.setAttribute("aria-label", label);
        button.textContent = glyph;
        return button;
    }

    const header = document.createElement("div");
    header.className = "jalali-picker-header";
    // Which side goes back, and which forward.
    //
    // Product owner, 2026-09-20: «جهت دکمه‌های `<` و `<<` با `>` و `>>`
    // جابه‌جا شود ... حرکت بصری درست باشد، نه فقط آیکون». So the two
    // functions swap sides: the **left** pair now goes back and the
    // **right** pair goes forward, each arrow still pointing outward at
    // its own edge. This is the arrangement of essentially every other
    // calendar a Persian user also has open — Google Calendar, a phone's
    // date picker — and the muscle memory that comes with it.
    //
    // Product owner, 2026-09-21: the two FullCalendar-based calendars
    // (`/leads/calendar/`, `/after-sales/calendar/`) still had prev on
    // the right in both their custom month-view buttons
    // (`jalaliCalendarButtons` below) and the vendor's own week/day
    // `prev`/`next` — the first because FullCalendar renders a
    // `headerToolbar` group with the same "first-authored sits
    // rightmost" rule as this row, and the button *names* were never
    // reordered to account for it; the second because it was originally
    // left as the vendor default. Both toolbar strings were reordered to
    // match this header (`jalaliCalendarButtons`, and the two
    // `headerToolbar.start` strings in `setupLeadCalendar`/
    // `setupAfterSalesCalendar`) — a reorder, not a re-skin, so no icon
    // or CSS override was needed there either. Verified in-browser: all
    // three controls now agree, next always ends up on the right.
    //
    // DOM order is visual order in this `dir="rtl"` row: first child
    // sits rightmost.
    const nextYearBtn = navButton("»", "سال بعد");
    const nextMonthBtn = navButton("›", "ماه بعد");
    const title = document.createElement("span");
    title.className = "jalali-picker-title";
    // The title is two buttons, not a label: the month name opens the
    // month grid and the year opens the decade. A reader who wants
    // «فروردین ۱۴۰۶» from «مهر ۱۴۰۵» should not have to press an arrow
    // six times.
    const monthBtn = document.createElement("button");
    monthBtn.type = "button";
    monthBtn.className = "btn btn-sm btn-light jalali-picker-scope";
    monthBtn.setAttribute("aria-label", "انتخاب ماه");
    const yearBtn = document.createElement("button");
    yearBtn.type = "button";
    yearBtn.className = "btn btn-sm btn-light jalali-picker-scope";
    yearBtn.setAttribute("aria-label", "انتخاب سال");
    title.append(monthBtn, yearBtn);
    const prevMonthBtn = navButton("‹", "ماه قبل");
    const prevYearBtn = navButton("«", "سال قبل");
    header.append(nextYearBtn, nextMonthBtn, title, prevMonthBtn, prevYearBtn);

    const weekdays = document.createElement("div");
    weekdays.className = "jalali-picker-weekdays";
    JALALI_WEEKDAY_LETTERS.forEach((letter) => {
        const cell = document.createElement("span");
        cell.textContent = letter;
        weekdays.append(cell);
    });

    const days = document.createElement("div");
    days.className = "jalali-picker-days";
    const months = document.createElement("div");
    months.className = "jalali-picker-months";
    months.hidden = true;
    const years = document.createElement("div");
    years.className = "jalali-picker-years";
    years.hidden = true;

    let timeRow = null;
    let hourField = null;
    let minuteField = null;
    if (wantsTime) {
        timeRow = document.createElement("div");
        timeRow.className = "jalali-picker-time";

        /**
         * One 24-hour time unit: a typable box with a step button above
         * and below it.
         *
         * A `<select>` with 24 options was what this used to be, and it
         * is the wrong control for a number with an order: picking 23:55
         * meant scrolling a list nearly to its end, twice. A stepper
         * reads as the number it is, takes ↑/↓ from the keyboard, wraps
         * at its own boundary, and still lets the exact value be typed
         * for the case the steps do not land on.
         */
        function timeUnit(label, max, step, initial, onChange) {
            const unit = document.createElement("div");
            unit.className = "jalali-picker-time-unit";

            const up = document.createElement("button");
            up.type = "button";
            up.className = "btn btn-icon btn-sm btn-light jalali-picker-time-step";
            up.textContent = "＋";
            up.setAttribute("aria-label", `${label} بیشتر`);

            const box = document.createElement("input");
            box.type = "text";
            box.inputMode = "numeric";
            box.className = "form-control form-control-sm form-control-solid jalali-picker-time-box";
            box.setAttribute("aria-label", label);
            box.setAttribute("role", "spinbutton");
            box.setAttribute("aria-valuemin", "0");
            box.setAttribute("aria-valuemax", String(max));

            const down = document.createElement("button");
            down.type = "button";
            down.className = "btn btn-icon btn-sm btn-light jalali-picker-time-step";
            down.textContent = "−";
            down.setAttribute("aria-label", `${label} کمتر`);

            let value = initial;
            function paint() {
                box.value = toPersianDigits(pad2(value));
                box.setAttribute("aria-valuenow", String(value));
                box.setAttribute("aria-valuetext", toPersianDigits(pad2(value)));
            }
            // Wrapping, not clamping: 23 + 1 is 00, which is what the
            // next hour actually is, and stopping dead at the top of the
            // range is the thing that makes a stepper tedious.
            function shift(delta) {
                value = (value + delta + (max + 1)) % (max + 1);
                paint();
                onChange(value);
            }
            up.addEventListener("click", () => shift(step));
            down.addEventListener("click", () => shift(-step));
            box.addEventListener("keydown", (event) => {
                if (event.key === "ArrowUp") { event.preventDefault(); shift(step); }
                else if (event.key === "ArrowDown") { event.preventDefault(); shift(-step); }
            });
            // Typed input is read on the way out, in either digit script,
            // and anything unusable falls back to what was showing rather
            // than to zero.
            box.addEventListener("change", () => {
                const typed = Number(toLatinDigits(box.value).replace(/\D/g, ""));
                if (Number.isFinite(typed) && typed >= 0 && typed <= max) value = typed;
                paint();
                onChange(value);
            });
            paint();
            unit.append(up, box, down);
            return unit;
        }

        const hourUnit = timeUnit("ساعت", 23, 1, hour, (next) => { hour = next; if (selected) commit(); });
        const separator = document.createElement("span");
        separator.className = "jalali-picker-time-separator";
        separator.textContent = ":";
        // Five minutes is the step people actually schedule on; the box
        // still takes any minute that is typed into it.
        const minuteUnit = timeUnit("دقیقه", 59, 5, minute, (next) => { minute = next; if (selected) commit(); });
        hourField = hourUnit.querySelector("input");
        minuteField = minuteUnit.querySelector("input");
        // Hour on the right, minute on the left — `HH:MM` reads
        // left-to-right even inside an RTL panel, the same way every
        // clock and every `dir="ltr"` money cell in this app does.
        timeRow.dir = "ltr";
        timeRow.append(hourUnit, separator, minuteUnit);
    }

    const footer = document.createElement("div");
    footer.className = "jalali-picker-footer";
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "btn btn-sm btn-light";
    clearBtn.textContent = "پاک‌کردن";
    const todayBtn = document.createElement("button");
    todayBtn.type = "button";
    todayBtn.className = "btn btn-sm btn-light-primary";
    todayBtn.textContent = "امروز";
    footer.append(clearBtn, todayBtn);
    let confirmBtn = null;
    if (wantsTime) {
        confirmBtn = document.createElement("button");
        confirmBtn.type = "button";
        confirmBtn.className = "btn btn-sm btn-primary";
        confirmBtn.textContent = "تأیید";
        footer.append(confirmBtn);
    }

    panel.append(header, weekdays, days, months, years, ...(timeRow ? [timeRow] : []), footer);

    //: The decade the year grid is showing, as its first year.
    let decadeStart = Math.floor(viewYear / 10) * 10;

    function updateTitle() {
        monthBtn.textContent = JALALI_MONTH_NAMES[viewMonth - 1];
        yearBtn.textContent = toPersianDigits(String(viewYear));
        monthBtn.setAttribute("aria-expanded", String(view === "months"));
        yearBtn.setAttribute("aria-expanded", String(view === "years"));
    }

    /**
     * Show one of the three grids.
     *
     * The weekday strip belongs to the day grid alone — left up in the
     * month and year views it would label columns that are not days.
     * The arrows keep working in every view and mean whatever the view
     * is made of: a month in the day view, a year in the month view, a
     * decade in the year view.
     */
    function setView(next) {
        view = next;
        weekdays.hidden = view !== "days";
        days.hidden = view !== "days";
        months.hidden = view !== "months";
        years.hidden = view !== "years";
        if (timeRow) timeRow.hidden = view !== "days";
        updateTitle();
        if (view === "days") renderDays();
        else if (view === "months") renderMonths();
        else renderYears();
    }

    function renderDays() {
        days.replaceChildren();
        const leading = jalaliWeekday(viewYear, viewMonth, 1);
        const length = jalaliMonthLength(viewYear, viewMonth);
        const totalCells = 42; // 6 full weeks, so the popup never resizes month to month.
        for (let cellIndex = 0; cellIndex < totalCells; cellIndex += 1) {
            const day = cellIndex - leading + 1;
            if (day < 1 || day > length) {
                days.append(document.createElement("span"));
                continue;
            }
            const isToday = viewYear === todayYear && viewMonth === todayMonth && day === todayDay;
            const isSelected = !!selected && selected.year === viewYear && selected.month === viewMonth && selected.day === day;
            const cell = document.createElement("button");
            cell.type = "button";
            cell.textContent = toPersianDigits(String(day));
            cell.className = "btn btn-icon jalali-picker-day " + (
                isSelected ? "btn-primary"
                : isToday ? "btn-active-light-primary border border-primary text-primary"
                : "btn-color-gray-700 btn-active-light-primary"
            );
            if (isSelected) cell.setAttribute("aria-current", "date");
            cell.addEventListener("click", () => {
                selected = {year: viewYear, month: viewMonth, day};
                commit();
                if (wantsTime) {
                    renderDays();
                } else {
                    close();
                }
            });
            days.append(cell);
        }
    }

    function renderMonths() {
        months.replaceChildren();
        JALALI_MONTH_NAMES.forEach((name, index) => {
            const monthNumber = index + 1;
            const isCurrent = viewYear === todayYear && monthNumber === todayMonth;
            const isSelected = !!selected && selected.year === viewYear && selected.month === monthNumber;
            const cell = document.createElement("button");
            cell.type = "button";
            cell.textContent = name;
            cell.className = "btn btn-sm jalali-picker-cell " + (
                isSelected ? "btn-primary"
                : isCurrent ? "btn-active-light-primary border border-primary text-primary"
                : "btn-color-gray-700 btn-active-light-primary"
            );
            cell.addEventListener("click", () => {
                viewMonth = monthNumber;
                // Back down to the days of the month just chosen, rather
                // than committing a date the reader has not picked a day
                // for yet.
                setView("days");
            });
            months.append(cell);
        });
    }

    function renderYears() {
        years.replaceChildren();
        // Twelve cells: the ten years of the decade plus the last year of
        // the one before and the first of the one after, so the grid is a
        // full 3×4 and stepping between decades has an obvious handhold
        // at each end.
        for (let offset = -1; offset <= 10; offset += 1) {
            const year = decadeStart + offset;
            const outside = offset < 0 || offset > 9;
            const isCurrent = year === todayYear;
            const isSelected = !!selected && selected.year === year;
            const cell = document.createElement("button");
            cell.type = "button";
            cell.textContent = toPersianDigits(String(year));
            cell.className = "btn btn-sm jalali-picker-cell " + (
                isSelected ? "btn-primary"
                : isCurrent ? "btn-active-light-primary border border-primary text-primary"
                : outside ? "btn-color-gray-500 btn-active-light-primary"
                : "btn-color-gray-700 btn-active-light-primary"
            );
            cell.addEventListener("click", () => {
                viewYear = year;
                decadeStart = Math.floor(year / 10) * 10;
                setView("months");
            });
            years.append(cell);
        }
    }

    function commit() {
        if (!selected) return;
        const text = wantsTime
            ? toPersianDigits(`${pad4(selected.year)}/${pad2(selected.month)}/${pad2(selected.day)} ${pad2(hour)}:${pad2(minute)}`)
            : toPersianDigits(`${pad4(selected.year)}/${pad2(selected.month)}/${pad2(selected.day)}`);
        field.value = text;
        dispatchUserEvent(field, "input");
        dispatchUserEvent(field, "change");
        field.dispatchEvent(new Event("blur"));
    }

    function shiftMonth(delta) {
        let year = viewYear;
        let month = viewMonth + delta;
        while (month < 1) { month += 12; year -= 1; }
        while (month > 12) { month -= 12; year += 1; }
        viewYear = year;
        viewMonth = month;
        decadeStart = Math.floor(viewYear / 10) * 10;
        updateTitle();
        renderDays();
    }

    /** One step back or forward, in whatever unit the current view shows. */
    function step(delta) {
        if (view === "days") { shiftMonth(delta); return; }
        if (view === "months") {
            viewYear += delta;
            decadeStart = Math.floor(viewYear / 10) * 10;
            updateTitle();
            renderMonths();
            return;
        }
        decadeStart += delta * 10;
        renderYears();
    }

    /** A year at a time in the day and month views, a decade in the year view. */
    function bigStep(delta) {
        if (view === "years") { decadeStart += delta * 100; renderYears(); return; }
        viewYear += delta;
        decadeStart = Math.floor(viewYear / 10) * 10;
        updateTitle();
        if (view === "days") renderDays(); else renderMonths();
    }

    prevMonthBtn.addEventListener("click", () => step(-1));
    nextMonthBtn.addEventListener("click", () => step(1));
    prevYearBtn.addEventListener("click", () => bigStep(-1));
    nextYearBtn.addEventListener("click", () => bigStep(1));
    monthBtn.addEventListener("click", () => setView(view === "months" ? "days" : "months"));
    yearBtn.addEventListener("click", () => setView(view === "years" ? "days" : "years"));

    clearBtn.addEventListener("click", () => {
        field.value = "";
        dispatchUserEvent(field, "input");
        dispatchUserEvent(field, "change");
        field.dispatchEvent(new Event("blur"));
        close();
    });
    todayBtn.addEventListener("click", () => {
        viewYear = todayYear;
        viewMonth = todayMonth;
        decadeStart = Math.floor(todayYear / 10) * 10;
        selected = {year: todayYear, month: todayMonth, day: todayDay};
        if (wantsTime) {
            hour = nowParts.hour;
            minute = nowParts.minute;
            if (hourField) {
                hourField.value = toPersianDigits(pad2(hour));
                hourField.setAttribute("aria-valuenow", String(hour));
            }
            if (minuteField) {
                minuteField.value = toPersianDigits(pad2(minute));
                minuteField.setAttribute("aria-valuenow", String(minute));
            }
        }
        setView("days");
        commit();
        if (!wantsTime) close();
    });
    confirmBtn?.addEventListener("click", () => close());

    function position() {
        const anchor = field.getBoundingClientRect();
        const panelRect = panel.getBoundingClientRect();
        const margin = 8;
        let top = anchor.bottom + margin;
        if (top + panelRect.height > window.innerHeight - margin) {
            top = Math.max(margin, anchor.top - panelRect.height - margin);
        }
        let left = anchor.right - panelRect.width;
        left = Math.min(Math.max(left, margin), window.innerWidth - margin - panelRect.width);
        panel.style.top = `${top}px`;
        panel.style.left = `${left}px`;
    }

    function onDocumentMouseDown(event) {
        if (panel.contains(event.target) || event.target === field) return;
        close();
    }
    function onKeyDown(event) {
        if (event.key === "Escape") {
            event.stopPropagation();
            // Escape steps back out of a drill-down before it closes the
            // picker: a reader who opened the year grid by accident
            // should get the days back, not lose the popup.
            if (view !== "days") { setView("days"); return; }
            close();
            field.focus();
        }
    }

    function close() {
        if (openJalaliPickerField !== field) return;
        document.removeEventListener("mousedown", onDocumentMouseDown, true);
        document.removeEventListener("keydown", onKeyDown, true);
        panel.remove();
        openJalaliPickerField = null;
        closeOpenJalaliPicker = null;
    }

    // A field inside a native <dialog> renders in the browser's own top
    // layer; a picker appended to <body> would paint *behind* the open
    // dialog's backdrop and be unreachable. Appending inside the dialog
    // keeps it in that same promoted stacking context. Neither this nor
    // <body> is `position: relative`, which is fine — the panel is
    // `position: fixed` (dolphin.css) and positioned in viewport
    // coordinates below, not relative to its parent.
    (field.closest("dialog") || document.body).appendChild(panel);
    setView("days");
    // Measured before it is shown: `.jalali-picker` has no size of its
    // own to reason about until its content exists, and `position()`
    // needs that real size to decide whether it fits below the field.
    panel.style.visibility = "hidden";
    panel.style.display = "flex";
    position();
    panel.style.visibility = "";
    panel.style.display = "";
    // `.show` added only now, after the panel already has its final
    // position — the theme's own fade/move-in animation
    // (`.menu-sub-dropdown.show`) plays from there, not from wherever
    // the hidden measurement pass happened to leave it.
    panel.classList.add("show");

    document.addEventListener("mousedown", onDocumentMouseDown, true);
    document.addEventListener("keydown", onKeyDown, true);

    openJalaliPickerField = field;
    closeOpenJalaliPicker = close;
}

/**
 * Give every Jalali input the same behaviour once, at start-up.
 *
 * Persian digits are accepted as typed and the field reports its own error
 * on blur, so a bad date is caught where it was entered rather than as a
 * 400 from the server after submit. `openJalaliPicker` above is a second,
 * additive way to fill the same field — typing still works exactly as it
 * did before that function existed.
 */
export function setupJalaliInputs(root = document) {
    root.querySelectorAll("input[data-jalali]").forEach((field) => {
        if (field.dataset.jalaliReady === "1") return;
        field.dataset.jalaliReady = "1";
        const wantsTime = field.dataset.jalali === "datetime";
        field.setAttribute("dir", "ltr");
        field.setAttribute("inputmode", "numeric");
        field.setAttribute("autocomplete", "off");
        if (!field.placeholder) {
            field.placeholder = wantsTime ? "۱۴۰۵/۰۵/۲۵ ۱۴:۳۰" : "۱۴۰۵/۰۵/۲۵";
        }
        field.addEventListener("focus", () => openJalaliPicker(field));
        field.addEventListener("click", () => openJalaliPicker(field));
        field.addEventListener("blur", () => {
            const target = document.querySelector(`[data-error-for="${field.name}"]`);
            if (!field.value.trim()) {
                if (target) target.textContent = "";
                field.setCustomValidity("");
                return;
            }
            try {
                parseJalaliInput(field.value, {requireTime: wantsTime});
                field.setCustomValidity("");
                if (target) target.textContent = "";
            } catch (error) {
                field.setCustomValidity(error.message);
                if (target) target.textContent = error.message;
            }
        });
    });
}
