"""Round 2 of the product owner's UI/UX follow-up (2026-09-21) — twelve fixes
and additions on top of the five batches already shipped as `2.14.0`.

One class per item, added as each item lands, in the same source-scanning
style as `test_ui_overhaul_*` (`ui_overhaul_helpers`): what a browser check
already confirmed once is pinned here against silent regressions, not
re-verified.
"""

from django.test import SimpleTestCase

from common.tests.ui_overhaul_helpers import CODE, SCRIPT, function_body, rule


class JalaliPickerTitleSpacingTests(SimpleTestCase):
    """Item 1 — the month/year title in the date picker read as one jumbled
    word: 2026-09-20 split it into two buttons (`monthBtn`/`yearBtn` in
    `openJalaliPicker`, dolphin-app.js) so each half opens its own grid, but
    both buttons carry the base `.btn` class the nav-arrow rule also
    selects — `.jalali-picker .jalali-picker-header .btn` forced them to a
    27px square meant for a lone icon, leaving ~0 content width once padding
    was accounted for. The text was clipped to an unreadable sliver.
    """

    def test_nav_arrow_rule_excludes_the_title_buttons(self):
        # The fixed-width icon-button rule must no longer also catch the
        # two title buttons — that was the whole bug.
        self.assertIn(
            ".jalali-picker .jalali-picker-header .btn:not(.jalali-picker-scope)",
            CODE,
        )

    def test_title_is_a_flex_row_with_a_real_gap(self):
        # `display:flex` + `gap` is what actually separates the two buttons;
        # without it they sat back to back with zero space between them
        # regardless of their own padding.
        body = rule(".jalali-picker-title")
        self.assertIn("display: flex", body)
        self.assertRegex(body, r"gap:\s*0\.3rem")

    def test_scope_padding_wins_over_the_vendor_button(self):
        # Metronic's own `.btn:not(...).btn-sm` (eight `:not()` clauses) has
        # higher specificity than any selector built from this component's
        # own classes, so the padding override needs `!important` to
        # actually apply — without it the buttons kept the vendor's roomy
        # text-button padding despite the width fix, which is what had
        # pushed a long month name out of the title's own space.
        body = rule(".jalali-picker .jalali-picker-scope")
        self.assertIn("!important", body)
        self.assertIn("overflow: hidden", body)


class LineChartAxisLabelTests(SimpleTestCase):
    """Item 2 — the bottom axis of every line/mixed chart (`renderAreaChart`,
    `renderMixedChart`) was truncating its own already-thinned date labels
    to unreadable garbage: measured live on the dashboard trend widget, a
    full `۱۴۰۵/۰۴/۱۵` came out `۱…`, and even the shortened `۰۴/۱۵` this fix
    introduces still came out `۰۴…` before `trim` was removed. The
    untruncated value only ever reached a hover `<title>` nobody finds.
    """

    def test_compact_axis_label_drops_the_year(self):
        body = function_body("compactAxisLabel", SCRIPT)
        self.assertIn('split("/")', body)
        self.assertIn("parts.length === 3", body)

    def test_thinning_formatter_shortens_surviving_labels(self):
        body = function_body("thinningFormatter", SCRIPT)
        self.assertIn("compactAxisLabel(value)", body)

    def test_neither_line_chart_lets_apex_trim_the_axis_text(self):
        # `trim: true` is what was chopping the already-short label down
        # further — removed from both chart functions, `hideOverlappingLabels`
        # stays as the real backstop against genuine overlap.
        for fn in ("renderAreaChart", "renderMixedChart"):
            body = function_body(fn, SCRIPT)
            self.assertNotIn("trim: true", body, f"{fn} still lets Apex trim its axis text")
            self.assertIn("hideOverlappingLabels: true", body)
