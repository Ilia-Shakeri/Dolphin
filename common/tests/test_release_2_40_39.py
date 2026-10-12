"""Back to colour, and the arrows turned round (2.40.39).

Product owner, 2026-10-12, after deploying 2.40.38: the widgets' coloured
icons and lines come back; the collapsed sidebar rings the current section;
a ring's centre figure is written in millions and billions; toggles move when
they change; the dialog close gets a faint red halo; and every < becomes >
and the other way round, across the panel.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "common" / "static" / "common"
JS = STATIC / "js"
CSS = (STATIC / "dolphin.css").read_text(encoding="utf-8")


class ColourTests(SimpleTestCase):
    def test_the_widgets_wear_their_own_colours_again(self):
        self.assertNotIn("[data-dashboard-grid] > .dashboard-widget { --dashboard-accent: var(--bs-primary); }", CSS)
        dashboard = (JS / "features" / "dashboard" / "dashboard.js").read_text(encoding="utf-8")
        self.assertEqual(dashboard.count('{accent: "primary"}'), 0)
        self.assertIn("renderSparkline(spark, kpi.spark, {accent: kpi.accent})", dashboard)

    def test_the_collapsed_rail_rings_the_current_section(self):
        self.assertIn(".app-sidebar:not(:hover) .app-sidebar-menu .menu > .menu-item.here > .menu-link {", CSS)


class RingTests(SimpleTestCase):
    def test_a_ring_centre_is_written_short(self):
        charts = (JS / "ui" / "charts.js").read_text(encoding="utf-8")
        self.assertIn("export function compactFigure(text)", charts)
        self.assertIn("compactFigure(displays[opts?.seriesIndex ?? 0] ?? _value)", charts)


class MotionTests(SimpleTestCase):
    def test_toggles_settle_when_they_change(self):
        self.assertIn("@keyframes dolphin-toggle-settle", CSS)
        self.assertIn(".btn-check:checked + .btn,", CSS)


class ArrowTests(SimpleTestCase):
    def test_the_calendars_arrows_are_turned_round(self):
        calendar = (JS / "ui" / "calendar.js").read_text(encoding="utf-8")
        self.assertIn('jalaliPrev: {icon: "chevron-left"', calendar)
        self.assertIn('stepPrev: {icon: "chevron-left"', calendar)
        self.assertIn('start: "jalaliPrev,jalaliNext,stepPrev,stepNext today"', calendar)

    def test_no_wizard_keeps_the_old_arrows(self):
        for path in (ROOT / "common" / "templates").rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r'data-dolphin-stepper-action="previous"><i class="([^"]+)"', text):
                with self.subTest(path=path.name):
                    self.assertNotIn("di-left", match.group(1))
