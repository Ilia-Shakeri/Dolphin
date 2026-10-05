"""The two calendars share one shell, and a moved event names the right instant (2.40.12).

`createJalaliCalendar` (`ui/calendar.js`) is the FullCalendar setup the
follow-up and after-sales calendars each used to carry in full. A moved
all-day event is stored as midnight in Tehran whatever the browser's own
time zone is (`calendarInstant`); `toISOString()` on the browser-local
midnight named the day before for a reader west of Tehran.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase

JS_ROOT = Path(__file__).resolve().parents[1] / "static" / "common" / "js"
NODE = shutil.which("node")
MODULES = ("core/api.js", "core/digits.js", "core/events.js", "core/form-errors.js", "core/jalali.js",
           "core/messages.js", "ui/jalali-picker.js", "ui/calendar.js")
LEAD = (JS_ROOT / "features" / "leads" / "lead-calendar.js").read_text(encoding="utf-8")
AFTER_SALES = (JS_ROOT / "features" / "after_sales" / "after-sales-calendar.js").read_text(encoding="utf-8")


class SharedShellTests(SimpleTestCase):
    def test_both_calendars_use_the_one_shell(self):
        for source in (LEAD, AFTER_SALES):
            self.assertIn("createJalaliCalendar({", source)
            self.assertNotIn("new FullCalendar.Calendar(", source)
            self.assertNotIn("toISOString()", source)

    def test_the_features_are_now_only_what_differs(self):
        self.assertLess(len(LEAD.splitlines()) + len(AFTER_SALES.splitlines()), 320)


@skipUnless(NODE, "node is not installed")
class CalendarInstantTests(SimpleTestCase):
    def run_in(self, zone):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for relative in MODULES:
                text = (JS_ROOT / relative).read_text(encoding="utf-8").replace('"dolphin/', f'"{tmp.as_uri()}/')
                target = tmp / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            probe = tmp / "probe.mjs"
            probe.write_text(
                f'import {{calendarInstant}} from "{(tmp / "ui/calendar.js").as_uri()}";\n'
                "const allDay = calendarInstant(new Date(2026, 9, 5), true);\n"
                "const timed = calendarInstant(new Date(Date.UTC(2026, 9, 5, 6, 0)), false);\n"
                "console.log(JSON.stringify([allDay, timed]));\n",
                encoding="utf-8",
            )
            done = subprocess.run([NODE, str(probe)], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                  timeout=60, env={**os.environ, "TZ": zone})
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_an_all_day_event_is_tehran_midnight_from_any_zone(self):
        for zone in ("Asia/Tehran", "America/New_York", "Asia/Tokyo"):
            with self.subTest(zone=zone):
                all_day, timed = self.run_in(zone)
                # 5 Oct 2026 00:00 in Tehran (+03:30) is 4 Oct 20:30 UTC.
                self.assertEqual(all_day, "2026-10-04T20:30:00.000Z")
                self.assertEqual(timed, "2026-10-05T06:00:00.000Z")
