"""Chart text stays outside the drawing, in both shared chart helpers.

Product-owner request (2026-09-04): a percentage printed on a thin donut
wedge either overlaps its neighbour or gets clipped past the ring's own
edge, and a value label drawn at the inside tip of a short bar is the same
colour the bar was filled — unreadable on a short bar, cramped on a long
one. `renderDonutChart` and `renderBarChart` in `common/static/common/
dolphin-app.js` are the two shared functions every chart in the panel is
drawn through (reports, the customer dashboard, list-page charts), so
fixing text placement there once fixes it everywhere at once.

Pinned by source pattern, the same way `test_dashboard_insights.py`'s
`ChartMountOrderTests` and `IconPathTests` already pin ApexCharts
configuration no Django test can execute.
"""

import pathlib

from django.test import SimpleTestCase

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
).read_text(encoding="utf-8")


def _function_body(name):
    start = SCRIPT.index(f"function {name}(")
    # Every chart function in this module is followed by another top-level
    # `function` declaration at the same four-space indent; the next one
    # marks this function's own end.
    end = SCRIPT.index("\n    function ", start + 1)
    return SCRIPT[start:end]


class DonutLabelTests(SimpleTestCase):
    body = _function_body("renderDonutChart")

    def test_no_text_is_drawn_on_the_wedges_themselves(self):
        self.assertIn("dataLabels: {enabled: false}", self.body)

    def test_the_percentage_moved_to_the_legend_instead_of_disappearing(self):
        """The information is not lost — it just lives somewhere with room."""
        self.assertIn("legend: {", self.body)
        self.assertIn("formatter: (label, opts) => {", self.body)
        self.assertIn("٪", self.body)


class BarLabelTests(SimpleTestCase):
    """Pinned against a live-measured fix, not the property names alone.

    Three things were tried before this one, each measured against a real
    rendered chart rather than assumed from an ApexCharts option's name:

    1. `plotOptions.bar.dataLabels.position: "top"` — reads like "draw the
       label past the bar's end" and does not, for a plain (non-stacked)
       horizontal bar; the anchor sat ~29px *inside* the tip regardless.
    2. A large `offsetX` alone with a percentage-padded axis — clears a
       short value-only label, but a name-and-value string is roughly
       twice as wide, and a flat percentage does not scale to that.
    3. A separate y-axis label column for the category name — Apex's own
       gutter-width calculation came out at 45px for Persian names that
       render 150–160px wide, so the bar's own opening third drew directly
       under its own name; `grid.padding.left` set to the correct width did
       not move that gutter by a single pixel.

    What actually holds: the category name joins the value as one combined
    label (`combined`), drawn through the offset+anchor mechanism that
    *does* work, with the y-axis column turned off outright; and the axis
    max is computed from the widest such label's real measured pixel width
    against the chart's own real rendered width, not a guessed percentage.
    """

    body = _function_body("renderBarChart")

    def test_the_key_and_the_value_are_one_combined_label(self):
        self.assertIn("`${item.label} — ${item.display ?? String(item.value)}`", self.body)
        self.assertIn("formatter: (_value, {dataPointIndex}) => combined[dataPointIndex]", self.body)

    def test_there_is_no_separate_column_for_the_category_name(self):
        self.assertIn("labels: {show: false}", self.body.split("yaxis: {")[1].split("},")[0] + "},")

    def test_the_offset_is_large_enough_to_actually_clear_the_bar(self):
        # Measured against the rendered chart: anchors a bar's own label
        # roughly 29px inside its tip regardless of `position`, so anything
        # under ~30 would still land back on the bar.
        offset = int(self.body.split("offsetX:")[1].split(",")[0].strip())
        self.assertGreater(offset, 30)

    def test_the_anchor_is_the_rtl_correct_one(self):
        self.assertIn('textAnchor: "end"', self.body)

    def test_the_axis_headroom_is_measured_not_guessed(self):
        """A flat percentage was the second cut here and did not scale to
        a name-and-value string roughly twice as wide as a value alone."""
        self.assertIn("measureTextWidth(text, LABEL_FONT)", self.body)
        self.assertIn("chart.clientWidth", self.body)
        self.assertNotIn("* 1.3", self.body)

    def test_the_label_colour_is_the_pages_own_ink_not_an_assumed_white(self):
        self.assertIn("colors: [chartInk().text]", self.body)


class AreaChartUnaffectedTests(SimpleTestCase):
    """The area chart never drew text on itself; nothing here should change it."""

    def test_area_chart_data_labels_stay_off(self):
        body = _function_body("renderAreaChart")
        self.assertIn("dataLabels: {enabled: false}", body)


class TextMeasurementHelperTests(SimpleTestCase):
    """The one small helper both fixes above lean on."""

    def test_the_helper_reuses_one_canvas_rather_than_allocating_per_call(self):
        start = SCRIPT.index("function measureTextWidth(")
        end = SCRIPT.index("\n    function ", start + 1)
        body = SCRIPT[start:end]
        self.assertIn("_measureCanvas ??=", body)
        self.assertIn("context.measureText(text).width", body)
