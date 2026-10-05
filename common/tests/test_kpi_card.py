"""The dashboard's one KPI card (2.40.3).

* the capability tiles and the insight KPIs are the same component;
* the chip and the sparkline come from real server data or are absent;
* every chip tone reads at 4.5:1 or better on its own tint, in both themes —
  computed here from the theme's own colours and the `color-mix` the CSS uses;
* no coloured glow is left on the boards, and the theme carries no invalid
  `box-shadow: false` declarations.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

from common.dashboard import _count_chip, _compared_caption, _kpi
from common.tests.panel_js import PANEL_SCRIPT

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
THEME = (ROOT / "common" / "static" / "common" / "ui" / "css" / "dolphin-theme.rtl.css").read_text(encoding="utf-8")
HOME = (ROOT / "common" / "templates" / "common" / "home.html").read_text(encoding="utf-8")
SCRIPT = PANEL_SCRIPT.read_text(encoding="utf-8")
TONES = ("primary", "success", "warning", "info", "danger")


def _theme_colours(selector_pattern):
    """Every hex colour token the theme sets under `selector_pattern`, later
    blocks overriding earlier ones — the cascade the browser applies."""
    colours = {}
    for match in re.finditer(selector_pattern, THEME):
        block = THEME[match.end():THEME.index("}", match.end())]
        colours.update(re.findall(r"(--bs-[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\s*;", block))
    return colours


def _rgb(hex_colour):
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, share_a):
    """`color-mix(in srgb, a share_a, b)`: per-channel, gamma-encoded."""
    return tuple(x * share_a + y * (1 - share_a) for x, y in zip(a, b))


def _luminance(rgb):
    def channel(value):
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ContrastTests(SimpleTestCase):
    def _ink_share(self, dark):
        pattern = (r"\[data-bs-theme=dark\] \.kpi-card \.kpi-chip \{ --kpi-chip-ink: color-mix\(in srgb, var\(--kpi-chip-tone\) (\d+)%, #fff\); \}"
                   if dark else
                   r"\.kpi-card \.kpi-chip \{ --kpi-chip-ink: color-mix\(in srgb, var\(--kpi-chip-tone\) (\d+)%, #000\); \}")
        return int(re.search(pattern, CSS).group(1)) / 100

    def _check(self, colours, background, *, dark):
        share = self._ink_share(dark)
        other = (255, 255, 255) if dark else (0, 0, 0)
        for tone in TONES:
            with self.subTest(tone=tone, dark=dark):
                tone_rgb = _rgb(colours[f"--bs-{tone}"])
                ink = _mix(tone_rgb, other, share)
                tint = _mix(tone_rgb, background, 0.14)
                self.assertGreaterEqual(_contrast(ink, tint), 4.5)

    def test_light_theme(self):
        colours = _theme_colours(r":root,\s*\[data-bs-theme=light\]\s*\{")
        self._check(colours, _rgb(colours["--bs-body-bg"]), dark=False)

    def test_dark_theme(self):
        colours = _theme_colours(r"\[data-bs-theme=dark\]\s*\{")
        self._check(colours, _rgb(colours["--bs-body-bg"]), dark=True)

    def test_the_caption_is_not_the_too_light_grey(self):
        rule = CSS.split(".kpi-card-caption {")[1].split("}")[0]
        self.assertIn("var(--bs-gray-700)", rule)


class ComponentTests(SimpleTestCase):
    def test_tiles_and_insights_are_one_component(self):
        self.assertIn('class="card card-flush h-100 text-decoration-none kpi-card"', HOME)
        self.assertIn('card.className = "card card-flush h-100 text-decoration-none kpi-card";', SCRIPT)
        for part in ("kpi-card-head", "kpi-card-title-row", "kpi-card-icon", "kpi-card-title"):
            self.assertIn(part, HOME)
            self.assertIn(part, SCRIPT)

    def test_no_line_under_three_points(self):
        self.assertIn("if (Array.isArray(kpi.spark) && kpi.spark.length >= 3) {", SCRIPT)
        self.assertIn("if (!el || !Array.isArray(values) || values.length < 3) return;", SCRIPT)

    def test_the_sparkline_has_a_text_alternative_and_a_last_point(self):
        self.assertIn('spark.setAttribute("role", "img");', SCRIPT)
        self.assertIn("dataPointIndex: values.length - 1", SCRIPT)

    def test_the_exact_figure_is_in_the_tooltip_and_the_label(self):
        self.assertIn('value.setAttribute("aria-label", kpi.full_display);', SCRIPT)

    def test_hover_changes_the_edge_only(self):
        hover = CSS.split("body:not(.dashboard-editing) [data-dashboard-grid] > .dashboard-widget > .card:hover {")[1].split("}")[0]
        self.assertNotIn("transform", hover)
        self.assertNotIn("box-shadow", hover)


class ServerDataTests(SimpleTestCase):
    def test_no_chip_without_a_real_count_or_base(self):
        self.assertIsNone(_count_chip(0, "تسویه‌نشده", "warning"))
        self.assertEqual(_count_chip(7, "تسویه‌نشده", "warning")["text"], "۷ تسویه‌نشده")
        self.assertIsNone(_kpi("k", "l", display="۱")["delta"])

    def test_the_caption_does_not_repeat_the_chip(self):
        self.assertEqual(_compared_caption(112, 100, noun="ماه"), "نسبت به همین بازه در ماه گذشته")
        # No base: the caption is the full sentence instead.
        self.assertIn("ثبت نشده", _compared_caption(5, 0, noun="ماه"))


class LeftoversTests(SimpleTestCase):
    def test_the_boards_carry_no_coloured_glow(self):
        rule = CSS.split("#order-board .kanban-board[data-accent] {\n    box-shadow:")[1].split("}")[0]
        self.assertEqual(rule.count("rgba("), 1)

    def test_the_theme_has_no_invalid_false_shadows(self):
        self.assertNotRegex(THEME, r"box-shadow:\s*false")
