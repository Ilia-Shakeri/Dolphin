"""Four smaller 2026-09-20 fixes that share one theme: things that were not
sitting where their own column or container said they were.

* **Action cells left the table.** `.row-actions` set `display: flex` on a
  `<td>`, and a table cell with a flex or grid display is no longer a table
  cell — it drops out of the table's column model and stops participating in
  column sizing. Reported on the cheques page («دکمه‌های عملیات ثبت باید در
  زیر ستون خودش باشد»), where two action columns sit side by side and the
  drift was finally visible; measured before the fix, nine columns matched
  their headers exactly while the tenth sat 79px off and the row's cells
  summed to 1251px against 1099px of headers. Every `.row-actions` table in
  the panel had the same latent drift.
* **The cheques page's four status buttons** now sit two-by-two instead of
  wrapping wherever the column width happened to put them.
* **The Jalali picker spilled its own days.** A bare `1fr` track is
  `minmax(auto, 1fr)`, whose `auto` floor is the cell's min-content width — so
  a day cell wider than its share widened the track instead of shrinking, and
  the row ran past the panel. Eight of thirty-one cells rendered outside it.
* **The picker's buttons** were sized for a lone icon button rather than a
  dense month grid: four 35px arrows filled 140px of a 208px header, leaving
  «شهریور ۱۴۰۵» exactly 69px of a 68px gap.

All read out of the shipped source. The rendered results were measured in a
browser at the time: every cheque column aligned to its header with the cells
summing to the headers exactly, zero day cells outside the picker, and all
twelve month names fitting their title without clipping.
"""

import pathlib

from django.test import SimpleTestCase


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")


def _rule(selector):
    return CSS.split(selector)[1].split("}")[0]


class ActionCellTests(SimpleTestCase):
    def test_an_action_cell_keeps_its_table_display(self):
        """The whole fix. A `<td>` that is flex or grid is not a table cell."""
        rule = _rule("\n.row-actions {")
        self.assertNotIn("display: flex", rule)
        self.assertNotIn("display: grid", rule)

    def test_the_buttons_are_still_spaced_and_centred(self):
        rule = _rule("\n.row-actions {")
        self.assertIn("text-align: center", rule)
        self.assertIn("margin-inline-start: 0.5rem", _rule(".row-actions > * + * {"))

    def test_the_two_by_two_grid_is_never_put_on_the_cell_itself(self):
        """It has to go on a wrapper inside the cell, for the same reason."""
        self.assertIn('actionGrid.className = "row-actions-2x2"', SCRIPT)
        self.assertIn("actions.appendChild(actionGrid)", SCRIPT)
        self.assertNotIn('className = "row-actions row-actions-2x2"', SCRIPT)

    def test_the_status_buttons_go_into_that_wrapper(self):
        self.assertIn("actionGrid.appendChild(button)", SCRIPT)

    def test_the_grid_is_two_columns(self):
        rule = _rule(".row-actions-2x2 {")
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", rule)

    def test_the_grid_owns_its_own_spacing(self):
        """Otherwise the inline margin rule for `.row-actions` children would
        apply on top of the grid's `gap`."""
        self.assertIn("gap: 0.5rem", _rule(".row-actions-2x2 {"))
        self.assertIn("margin-inline-start: 0", _rule(".row-actions-2x2 > * + * {"))


class JalaliPickerGridTests(SimpleTestCase):
    def test_the_day_grid_cannot_be_widened_by_its_cells(self):
        rule = _rule(".jalali-picker-weekdays,\n.jalali-picker-days {")
        self.assertIn("repeat(7, minmax(0, 1fr))", rule)
        self.assertNotIn("repeat(7, 1fr)", rule)

    def test_the_day_cell_override_is_specific_enough_to_win(self):
        """It used to be a single-class `.jalali-picker-day`, which scores
        below the vendor's own two-class `.btn.btn-icon` — so the override
        silently lost and every cell kept the vendor width."""
        self.assertIn(".jalali-picker .jalali-picker-day {", CSS)
        rule = _rule(".jalali-picker .jalali-picker-day {")
        self.assertIn("width: 2.1rem", rule)
        self.assertIn("min-width: 0", rule)

    def test_the_nav_buttons_are_sized_to_the_grid_they_sit_above(self):
        rule = _rule(".jalali-picker .jalali-picker-header .btn {")
        self.assertIn("width: 2.1rem", rule)
        self.assertIn("flex: 0 0 auto", rule)

    def test_the_month_title_can_shrink_instead_of_pushing_the_arrows(self):
        rule = _rule(".jalali-picker-title {")
        self.assertIn("min-width: 0", rule)
        self.assertIn("white-space: nowrap", rule)
        self.assertIn("text-overflow: ellipsis", rule)

    def test_the_footer_shortcuts_share_the_row(self):
        """«امروز» and «پاک‌کردن» are peers, and `space-between` left 148px of
        dead space between them in a 228px panel."""
        rule = _rule(".jalali-picker-footer {")
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", rule)
        self.assertNotIn("space-between", rule)


class UserStatusColumnTests(SimpleTestCase):
    """«ستون وضعیت باید رنگ داشته باشد» — user administration was the one
    table still painting its status with a local class that rendered as bold
    text, so «غیرفعال» did not stand out from «فعال» at a glance."""

    def test_the_users_table_uses_the_shared_status_badge(self):
        start = SCRIPT.index("function userRow(")
        body = SCRIPT[start:SCRIPT.index("\n    function ", start + 1)]
        self.assertIn("appendStatusCell(row, user.is_active)", body)
        self.assertNotIn('status.className = `status', body)

    def test_that_helper_paints_both_states(self):
        start = SCRIPT.index("function appendStatusCell(")
        body = SCRIPT[start:SCRIPT.index("\n    function ", start + 1)]
        self.assertIn("badge-light-success", body)
        self.assertIn("badge-light-danger", body)
