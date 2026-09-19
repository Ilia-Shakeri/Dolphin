"""Two display contracts asked for on 2026-09-19.

* Item 8 — «تابلوی سرنخ‌ها و تابلوی سفارش‌ها، هر ستون باید یه هاله رنگی شبیه به
  وضعیتش داشته باشه». The halo is worth pinning not because a colour is fragile
  but because *where the colour comes from* is: it must be `STATUS_ACCENTS`,
  the one table every document list already paints its badges from, so the
  column a cancelled lead sits in is the same red its own row is. A second,
  board-local colour list would drift from it the first time a status changed.

* Item 6 — «نیم ساعت نباید وجود داشته باشه و فقط باید ساعت باشه» for the week
  and day views of both calendars. FullCalendar's `slotDuration` defaults to
  thirty minutes, which drew a second unlabelled rule through every hour of a
  product where nothing is ever scheduled on a half hour.

Both are read out of the shipped source rather than a browser, so neither can
pass while the file says otherwise. The rendered result of both was checked in
a browser at the time (halo shadows and header tints measured per column;
`fc-timegrid-slot-minor` counted at zero in week and day view).
"""

import pathlib

from django.test import SimpleTestCase


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")

#: The statuses the two boards actually build columns from — leads from
#: `LEAD_STATUS_LABELS`, orders from `ORDER_TRANSITIONS`. Listed here because
#: this file cannot execute JavaScript; every one is asserted to exist in
#: `STATUS_ACCENTS` below, which is what keeps the list honest.
BOARD_STATUSES = ["pending", "completed", "cancelled", "draft", "confirmed", "fulfilled"]


def _function_body(name):
    start = SCRIPT.index(f"function {name}(")
    following = SCRIPT.find("\n    function ", start + 1)
    return SCRIPT[start:following if following != -1 else len(SCRIPT)]


def _status_accents():
    """`STATUS_ACCENTS` as a dict, parsed out of the source."""
    block = SCRIPT.split("const STATUS_ACCENTS = Object.freeze({")[1].split("});")[0]
    accents = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        key, _, value = line.partition(":")
        accents[key.strip()] = value.strip().strip(',').strip('"')
    return accents


class BoardColumnAccentTests(SimpleTestCase):
    def test_the_accent_comes_from_the_one_shared_status_table(self):
        body = _function_body("paintBoardColumns")
        self.assertIn("STATUS_ACCENTS[status]", body)
        self.assertIn('board.dataset.accent', body)

    def test_both_boards_paint_their_columns(self):
        """One call each, not one board remembering and the other forgetting."""
        self.assertEqual(SCRIPT.count("paintBoardColumns(container, STATUSES);"), 2)

    def test_every_status_a_board_shows_has_an_accent(self):
        accents = _status_accents()
        for status in BOARD_STATUSES:
            with self.subTest(status=status):
                self.assertIn(status, accents)

    def test_every_accent_those_statuses_use_is_styled(self):
        """A `data-accent` with no matching rule is a column with no halo —
        which reads as a column that failed to load, not as a plain one."""
        accents = _status_accents()
        for status in BOARD_STATUSES:
            accent = accents[status]
            with self.subTest(status=status, accent=accent):
                self.assertIn(f'#order-board .kanban-board[data-accent="{accent}"] {{', CSS)

    def test_an_unknown_status_still_gets_a_halo(self):
        """`secondary` is the fallback in `paintBoardColumns`, so it has to be
        one of the styled accents too."""
        self.assertIn('#order-board .kanban-board[data-accent="secondary"] {', CSS)
        self.assertIn('|| "secondary"', _function_body("paintBoardColumns"))

    def test_the_halo_is_built_from_theme_tokens_not_fixed_colours(self):
        """Every accent block points at `--bs-*` variables, which the theme
        redefines for dark mode — so the halo follows the theme."""
        block = CSS.split('#order-board .kanban-board[data-accent="primary"] {')[1].split("}")[0]
        self.assertIn("var(--bs-primary)", block)
        self.assertIn("var(--bs-primary-light)", block)
        self.assertIn("var(--bs-primary-rgb)", block)

    def test_the_halo_moves_no_geometry(self):
        """A shadow and a pseudo-element, not a border and not padding: the
        columns must sit exactly where they sat before."""
        rule = CSS.split("#order-board .kanban-board[data-accent] {")[1].split("}")[0]
        self.assertIn("box-shadow:", rule)
        self.assertNotIn("border-width", rule)
        self.assertNotIn("padding", rule)

    def test_the_tinted_header_rounds_itself_rather_than_being_clipped(self):
        """`overflow: hidden` on the column would also have to be trusted not
        to cut a card mid-drag; two corners are not worth that."""
        rule = CSS.split("#order-board .kanban-board[data-accent] header {")[1].split("}")[0]
        self.assertIn("border-start-start-radius", rule)
        self.assertNotIn("overflow: hidden", CSS.split("#order-board .kanban-board[data-accent] {")[1].split("}")[0])


class CalendarTimeGridTests(SimpleTestCase):
    def test_slots_are_whole_hours(self):
        block = SCRIPT.split("const CALENDAR_TIME_GRID_OPTIONS = {")[1].split("};")[0]
        self.assertIn('slotDuration: "01:00:00"', block)
        self.assertIn('slotLabelInterval: "01:00:00"', block)

    def test_both_calendars_use_the_same_options(self):
        """Lead follow-up and after-sales are the two calendars this product
        has; a fix applied to one of them is the bug this asserts against."""
        self.assertEqual(SCRIPT.count("...CALENDAR_TIME_GRID_OPTIONS,"), 2)

    def test_the_week_and_day_views_show_where_now_is(self):
        block = SCRIPT.split("const CALENDAR_TIME_GRID_OPTIONS = {")[1].split("};")[0]
        self.assertIn("nowIndicator: true", block)

    def test_two_appointments_in_one_hour_are_drawn_side_by_side(self):
        block = SCRIPT.split("const CALENDAR_TIME_GRID_OPTIONS = {")[1].split("};")[0]
        self.assertIn("slotEventOverlap: false", block)

    def test_no_hours_are_hidden_from_the_grid(self):
        """Narrowing to working hours would compact the view by silently not
        drawing a follow-up timed outside it. A calendar that omits an
        appointment is not a tidier calendar.

        Matched with the colon, because the reasoning above is also written out
        in a comment beside the options themselves and must stay there."""
        self.assertNotIn("slotMinTime:", SCRIPT)
        self.assertNotIn("slotMaxTime:", SCRIPT)

    def test_the_hour_axis_is_styled_for_both_calendars(self):
        for calendar in ("#lead-calendar", "#after-sales-calendar"):
            with self.subTest(calendar=calendar):
                self.assertIn(f"{calendar} .fc-timegrid-slot-label", CSS)
                self.assertIn(f"{calendar} .fc-timegrid-now-indicator-line", CSS)

    def test_the_now_line_and_today_column_read_from_theme_tokens(self):
        rule = CSS.split("#after-sales-calendar .fc-timegrid-now-indicator-line {")[1].split("}")[0]
        self.assertIn("var(--bs-danger)", rule)
        self.assertIn("rgba(var(--bs-primary-rgb), 0.06)", CSS)

    def test_the_grid_is_not_capped_and_scrolled(self):
        """Tried and reverted: FullCalendar 5's `height` is a calendar-level
        option, so capping the week view means setting it from `datesSet`, and
        the re-render that triggers rebuilds the toolbar title *after* this
        file has replaced it with its Jalali equivalent — measured, and it
        printed «شهریور ۱۴۰۵Sep 19 – 25, 2026»."""
        self.assertNotIn("syncCalendarHeight", SCRIPT)


class CampaignResultStatusTests(SimpleTestCase):
    """Item 7 — «در صفحه نتایج کمپین‌ها، در جدول، ستون وضعیت باید رنگ داشته
    باشد برای فهم بهتر». It was the one document list still printing its
    status as bare text."""

    def test_the_status_cell_is_the_shared_badge(self):
        body = _function_body("saleRow")
        self.assertIn("appendStatusBadgeCell(row, SALE_STATUS_TEXT, sale.status)", body)

    def test_both_sale_statuses_are_already_in_the_shared_accent_table(self):
        accents = _status_accents()
        self.assertEqual(accents["confirmed"], "success")
        self.assertEqual(accents["cancelled"], "danger")
