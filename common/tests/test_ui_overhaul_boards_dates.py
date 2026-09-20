"""Batch A of the 2026-09-20 UI/UX request: the kanban boards, the one date
picker, and the two calendars.

These are visual changes, so most of what matters was checked in a real
browser (recorded in `PROGRESS.md` and the changelog). What is pinned here
is the part a browser check cannot protect: the rules that are easy to undo
by accident later, each with the reason it exists.

Three of them are worth naming up front:

* **The kanban card body must not navigate.** It used to, and every attempt
  to drag a card was a coin-flip between moving it and leaving the page.
  The three-dot control is now the only way in, which is also why it had to
  grow to a real target size.
* **There is exactly one date picker.** A second implementation is how RTL
  bugs come back one page at a time.
* **The month view must be a *Jalali* month.** FullCalendar's own
  `dayGridMonth` is Gregorian, so a grid titled «مهر» held half of شهریور
  and stopped before مهر ended.
"""

import pathlib
import re

from django.test import SimpleTestCase

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "common" / "templates"


#: The stylesheet with its comments removed.
#:
#: Every rule below asks what the CSS *does*, and the comments beside those
#: rules explain at length why they do not do the thing being checked for —
#: so a scan over the raw text matches the explanation and fails. This is
#: the same reason `test_panel_backups.code_only` exists for the shell
#: scripts.
CODE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def rule(selector, source=None):
    """The declarations of the first rule whose selector list contains
    `selector`, as one string. Comment-free unless asked otherwise."""
    for block in (source or CODE).split("}"):
        if "{" not in block:
            continue
        head, body = block.split("{", 1)
        if selector in head:
            return body
    return ""


class KanbanCardTests(SimpleTestCase):
    def test_neither_board_navigates_from_the_card_body(self):
        """jKanban's `click` option fires for the whole item. With it gone,
        the only thing that can navigate is the anchor in the corner."""
        for board in ("setupLeadBoard", "setupOrderBoard"):
            body = SCRIPT.split(f"function {board}(", 1)[1].split("\n    async function", 1)[0]
            self.assertIn("new jKanban({", body, board)
            self.assertNotIn("click: (el) =>", body, board)

    def test_dragging_is_still_configured(self):
        """The reason the click handler went is that it fought the drag —
        so the drag itself had better still be there."""
        for board in ("setupLeadBoard", "setupOrderBoard"):
            body = SCRIPT.split(f"function {board}(", 1)[1].split("\n    async function", 1)[0]
            self.assertIn("dragItems: canManage", body, board)
            self.assertIn("dropEl:", body, board)

    def test_the_card_control_is_a_real_anchor(self):
        """Not a `div` with a click handler: an `<a href>` is what makes it
        reachable by keyboard, middle-clickable and openable in a new tab —
        none of which the `window.location` it replaced could do."""
        header = SCRIPT.split("function boardCardHeader(", 1)[1].split("\n    function ", 1)[0]
        self.assertIn('document.createElement("a")', header)
        self.assertIn("more.href = href", header)
        self.assertIn("aria-label", header)

    def test_the_control_is_at_least_a_32px_target(self):
        """«تارگت کلیک حداقل ۳۲×۳۲». This theme's root is 13px, so the rule
        is written in rem and has to clear 32px there."""
        declarations = rule("#order-board .kanban-card-more")
        size = re.search(r"width:\s*([\d.]+)rem", declarations)
        self.assertIsNotNone(size, declarations)
        self.assertGreaterEqual(float(size.group(1)) * 13, 32)

    def test_the_control_is_drawn_rather_than_ghosted(self):
        """It used to sit at 0.55 opacity because the whole card was
        clickable and this was a shortcut. Now it is the only door."""
        declarations = rule("#order-board .kanban-card-more")
        self.assertNotIn("opacity", declarations)

    def test_keyboard_focus_is_distinguishable_from_hover(self):
        self.assertIn("#order-board .kanban-card-more:focus-visible", CSS)
        self.assertIn("box-shadow", rule("#order-board .kanban-card-more:focus-visible"))


class SharedScrollbarTests(SimpleTestCase):
    """One scrollbar component, not one per panel."""

    def test_the_boards_use_the_shared_component(self):
        self.assertEqual(SCRIPT.count('classList.add("dolphin-hover-scroll")'), 2)
        self.assertNotIn("hover-scroll-overlay-y", SCRIPT)

    def test_it_puts_the_bar_on_the_right_in_an_rtl_panel(self):
        """No property positions a scrollbar. Flipping the scroll container
        to `ltr` and its children back to `rtl` is the only way, so if this
        pair ever separates the bar silently returns to the left."""
        declarations = rule(".dolphin-hover-scroll")
        self.assertIn("direction: ltr", declarations)
        self.assertIn("direction: rtl", rule(".dolphin-hover-scroll > *"))

    def test_both_engines_are_handled_separately(self):
        """Firefox has `scrollbar-color`; WebKit has a pseudo-element. They
        share nothing, so each is declared on its own."""
        self.assertIn("scrollbar-color", rule(".dolphin-hover-scroll"))
        self.assertIn(".dolphin-hover-scroll::-webkit-scrollbar-thumb", CSS)

    def test_it_stays_usable_without_a_hover(self):
        """A phone never hovers. Without this the bar would be permanently
        invisible there — worse than the default it replaced.

        The sheet has more than one `hover: none` block (the coarse-pointer
        table rules are older), so this looks for the one that is about the
        scrollbar rather than for whichever comes first in the file.
        """
        blocks = CODE.split("@media (hover: none)")[1:]
        touch = [block for block in blocks if "scrollbar" in block.split("\n}\n", 1)[0]]
        self.assertTrue(touch, "no touch fallback for the shared scrollbar")
        self.assertIn("scrollbar-color", touch[0])
        self.assertIn("-webkit-scrollbar-thumb", touch[0])

    def test_the_column_gap_clears_the_bar_on_the_side_it_is_on(self):
        """`padding-inline-end` would put the gap on the left here, because
        the container is deliberately `ltr`."""
        declarations = rule("#order-board .kanban-drag")
        self.assertIn("padding-right", declarations)
        self.assertNotIn("padding-inline-end", declarations)


class DatePickerTests(SimpleTestCase):
    def test_there_is_exactly_one_picker(self):
        self.assertEqual(SCRIPT.count("function openJalaliPicker("), 1)
        for rival in ("flatpickr", "persianDatepicker", "datepicker(", "new Pikaday"):
            self.assertNotIn(rival, SCRIPT, rival)

    def test_every_jalali_field_goes_through_it(self):
        self.assertIn("input[data-jalali]", SCRIPT)

    def test_the_left_pair_goes_back_and_the_right_pair_forward(self):
        """Product owner, 2026-09-20: the two functions swap sides. DOM
        order is visual order in this RTL row — first child is rightmost —
        so `next` first and `prev` last is left-goes-back."""
        header = SCRIPT.split("const header = document.createElement", 1)[1]
        self.assertIn(
            "header.append(nextYearBtn, nextMonthBtn, title, prevMonthBtn, prevYearBtn);",
            header,
        )

    def test_each_arrow_points_at_its_own_edge(self):
        picker = SCRIPT.split("function openJalaliPicker(", 1)[1]
        self.assertIn('navButton("»", "سال بعد")', picker)
        self.assertIn('navButton("›", "ماه بعد")', picker)
        self.assertIn('navButton("‹", "ماه قبل")', picker)
        self.assertIn('navButton("«", "سال قبل")', picker)

    def test_the_title_opens_a_month_grid_and_a_year_grid(self):
        picker = SCRIPT.split("function openJalaliPicker(", 1)[1]
        self.assertIn("function renderMonths()", picker)
        self.assertIn("function renderYears()", picker)
        self.assertIn('monthBtn.addEventListener("click"', picker)
        self.assertIn('yearBtn.addEventListener("click"', picker)

    def test_the_year_grid_is_a_decade(self):
        picker = SCRIPT.split("function renderYears()", 1)[1].split("\n        }", 1)[0]
        self.assertIn("decadeStart", picker)

    def test_the_weekday_strip_belongs_to_the_day_view_alone(self):
        """Left up in the month or year grid it would label columns that are
        not days."""
        view = SCRIPT.split("function setView(next)", 1)[1].split("\n        }", 1)[0]
        self.assertIn('weekdays.hidden = view !== "days"', view)

    def test_escape_steps_back_out_of_a_drill_down_before_closing(self):
        picker = SCRIPT.split("function onKeyDown(event)", 1)[1].split("\n        }", 1)[0]
        self.assertIn('if (view !== "days") { setView("days"); return; }', picker)

    def test_the_time_control_is_a_stepper_not_a_dropdown(self):
        """24 options in a `<select>` meant scrolling nearly to the end to
        reach 23:55, twice."""
        picker = SCRIPT.split("function openJalaliPicker(", 1)[1]
        self.assertIn("function timeUnit(", picker)
        self.assertNotIn('hourSelect = document.createElement("select")', picker)

    def test_the_time_stepper_takes_the_keyboard(self):
        unit = SCRIPT.split("function timeUnit(", 1)[1].split("\n            }", 1)[0]
        self.assertIn('event.key === "ArrowUp"', unit)
        self.assertIn('event.key === "ArrowDown"', unit)
        self.assertIn('role", "spinbutton"', unit)

    def test_the_time_stepper_wraps_rather_than_stopping_dead(self):
        unit = SCRIPT.split("function timeUnit(", 1)[1].split("\n            }", 1)[0]
        self.assertIn("(value + delta + (max + 1)) % (max + 1)", unit)

    def test_a_typed_time_is_read_in_either_digit_script(self):
        unit = SCRIPT.split("function timeUnit(", 1)[1].split("\n            }", 1)[0]
        self.assertIn("toLatinDigits(box.value)", unit)

    def test_the_time_row_reads_left_to_right(self):
        """`HH:MM` is an LTR run even inside an RTL panel, the same as every
        `dir="ltr"` money cell in this app."""
        self.assertIn('timeRow.dir = "ltr";', SCRIPT)


class SchedulingFieldsTests(SimpleTestCase):
    """«هر جا که منطقی است ... انتخاب ساعت هم داشته باشد» — the two fields
    whose model column is a `DateTimeField` and whose meaning is a scheduled
    moment. The time was already being sent (`apiDateTime`); the field just
    never let anyone enter one.
    """

    SCHEDULING = {
        "leads/list.html": "create-lead-follow-up",
        "leads/detail.html": "edit-lead-follow-up",
        "orders/list.html": "create-order-delivery",
        "orders/detail.html": "edit-order-delivery",
    }

    def test_they_ask_for_a_time(self):
        for page, field_id in self.SCHEDULING.items():
            text = (TEMPLATES / "common" / page).read_text(encoding="utf-8")
            fragment = text.split(f'id="{field_id}"', 1)[1].split(">", 1)[0]
            self.assertIn('data-jalali="datetime"', fragment, page)

    def test_the_edit_forms_put_the_time_back(self):
        """A date-only string in a `datetime` field fails that field's own
        blur validation and opens the picker on today instead of on the
        stored value."""
        self.assertIn(
            'document.getElementById("edit-lead-follow-up").value = localDateTimeValue(',
            SCRIPT,
        )
        self.assertIn(
            'document.getElementById("edit-order-delivery").value = localDateTimeValue(',
            SCRIPT,
        )

    def test_a_date_that_is_a_date_was_left_alone(self):
        """A cheque's due date and an invoice's document date are dates in
        law, not moments. Widening them would have been change for its own
        sake."""
        payments = (TEMPLATES / "common" / "payments" / "list.html").read_text(encoding="utf-8")
        due = payments.split('id="create-cheque-due"', 1)[1].split(">", 1)[0]
        self.assertIn('data-jalali="date"', due)


class JalaliMonthViewTests(SimpleTestCase):
    def test_the_month_view_is_a_jalali_month(self):
        """FullCalendar's own `dayGridMonth` is Gregorian, which is why a
        grid titled «مهر» never showed all of مهر."""
        self.assertIn("const JALALI_MONTH_VIEW = {", SCRIPT)
        self.assertIn("visibleRange: (current) => jalaliMonthRange(current)", SCRIPT)
        self.assertEqual(SCRIPT.count('initialView: "jalaliMonth"'), 2)

    def test_the_range_ends_the_day_after_the_last_one(self):
        """FullCalendar ranges are end-exclusive; an inclusive end would
        drop the 30th or 31st — the exact day the request was about."""
        body = SCRIPT.split("function jalaliMonthRange(", 1)[1].split("\n    }", 1)[0]
        self.assertIn("jalaliMonthLength(year, month)", body)
        self.assertIn("endD + 1", body)

    def test_stepping_a_month_is_jalali_arithmetic_not_a_fixed_duration(self):
        """A Jalali month is 29, 30 or 31 days depending on which one and
        which year, so FullCalendar's own prev/next cannot do it."""
        self.assertIn("function shiftJalaliMonth(", SCRIPT)
        self.assertIn("customButtons: jalaliCalendarButtons(() => calendar)", SCRIPT)

    def test_both_navigation_pairs_are_in_the_toolbar(self):
        """Only one pair is shown at a time, but both have to exist for
        `datesSet` to swap them — with the custom pair alone, week and day
        view would have had no navigation at all."""
        self.assertIn('start: "jalaliPrev,jalaliNext,prev,next today"', SCRIPT)
        self.assertEqual(SCRIPT.count(".fc-jalaliPrev-button, .fc-jalaliNext-button"), 2)

    def test_cell_numbers_are_month_view_only(self):
        """In week and day view the column header already carries the date;
        a number repeated in every hour cell was that date written again."""
        self.assertEqual(
            SCRIPT.count('arg.view.type === "jalaliMonth" ? jalaliDayLabel(arg.date) : ""'), 2,
        )

    def test_the_old_gregorian_view_name_is_gone(self):
        self.assertNotIn('"dayGridMonth"', SCRIPT.replace("FullCalendar's own `dayGridMonth`", ""))


class CalendarCellTests(SimpleTestCase):
    def test_a_day_has_a_surface_of_its_own(self):
        declarations = rule("#after-sales-calendar .fc-daygrid-day-frame")
        self.assertIn("border-radius", declarations)
        self.assertIn("background-color", declarations)

    def test_a_cell_grows_when_it_fills_up_and_eases_into_it(self):
        base = rule("#after-sales-calendar .fc-daygrid-day-frame")
        filled = rule("#after-sales-calendar .fc-daygrid-day-frame:has(.fc-daygrid-event)")
        self.assertIn("min-height", base)
        self.assertIn("min-height", filled)
        self.assertIn("transition: min-height", base)

    def test_the_height_transition_is_on_min_height_not_height(self):
        """The rows are laid out by FullCalendar in JavaScript; a transition
        on `height` fights it on every recalculation."""
        base = rule("#after-sales-calendar .fc-daygrid-day-frame")
        self.assertNotIn("transition: height", base)

    def test_reduced_motion_is_honoured(self):
        self.assertIn("prefers-reduced-motion", CSS)
        reduced = CSS.rsplit("@media (prefers-reduced-motion: reduce)", 1)[1]
        self.assertIn("fc-daygrid-day-frame", reduced)
