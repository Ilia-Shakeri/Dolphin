"""The month grid shows every Jalali month whole, in every year (2.34.9).

`jalaliMonthRange` and `shiftJalaliMonth` are the arithmetic behind both
calendars' month view and behind dragging an event across months. They are
checked here against the server's own Jalali implementation (`common.jalali`)
for the twelve months of ordinary and leap years, so a month that is one day
short, long, or off by a boundary cannot reach the screen.
"""

import datetime
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase

from common import jalali

JS_ROOT = Path(__file__).resolve().parents[1] / "static" / "common" / "js"
NODE = shutil.which("node")

PROBE = """
import {jalaliMonthRange, shiftJalaliMonth} from "%(calendar)s";
const out = {ranges: [], shifts: []};
for (const [year, month] of %(months)s) {
    const middle = new Date(%(mid)s[year + "-" + month]);
    const range = jalaliMonthRange(middle);
    out.ranges.push([year, month, range.start.toDateString(), range.end.toDateString()]);
}
for (const [iso, delta] of %(shifts)s) {
    out.shifts.push([iso, delta, shiftJalaliMonth(new Date(iso + "T12:00:00"), delta).toDateString()]);
}
console.log(JSON.stringify(out));
"""


def month_length(year, month):
    first = jalali.from_jalali(year, month, 1)
    nxt = jalali.from_jalali(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return first, (nxt - first).days


@skipUnless(NODE, "node is not installed")
class JalaliMonthRangeTests(SimpleTestCase):
    def run_probe(self, months, shifts):
        mids = {}
        for year, month in months:
            first, length = month_length(year, month)
            mids[f"{year}-{month}"] = (
                datetime.datetime.combine(first + datetime.timedelta(days=length // 2), datetime.time(12))
            ).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # The panel's bare `dolphin/...` specifiers resolve through an
            # import map in the browser; here they point at a copy on disk.
            for relative in ("core/digits.js", "core/events.js", "core/jalali.js", "ui/jalali-picker.js", "ui/calendar.js"):
                text = (JS_ROOT / relative).read_text(encoding="utf-8")
                text = text.replace('"dolphin/', f'"{(tmp).as_uri()}/')
                target = tmp / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            probe = tmp / "probe.mjs"
            probe.write_text(
                PROBE % {
                    "calendar": (tmp / "ui/calendar.js").as_uri(),
                    "months": json.dumps(months),
                    "mid": json.dumps(mids),
                    "shifts": json.dumps(shifts),
                },
                encoding="utf-8",
            )
            done = subprocess.run(
                [NODE, str(probe)], capture_output=True, text=True,
                stdin=subprocess.DEVNULL, timeout=60, env={**os.environ, "TZ": "Asia/Tehran"},
            )
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_every_month_of_ordinary_and_leap_years_is_shown_whole(self):
        # 1403 and 1408 are leap years: Esfand has thirty days there.
        months = [(year, month) for year in (1403, 1404, 1405, 1408) for month in range(1, 13)]
        result = self.run_probe(months, [])
        for year, month, start, end in result["ranges"]:
            first, length = month_length(year, month)
            self.assertEqual(start, first.strftime("%a %b %d %Y"), (year, month))
            after = first + datetime.timedelta(days=length)
            self.assertEqual(end, after.strftime("%a %b %d %Y"), (year, month))

    def test_stepping_crosses_year_boundaries_in_both_directions(self):
        shifts = [
            ("2026-03-25", 1),   # Esfand 1404 → Farvardin 1405
            ("2026-03-21", -1),  # Farvardin 1405 → Esfand 1404
            ("2026-10-03", 12),
            ("2026-10-03", -12),
        ]
        result = self.run_probe([], shifts)
        for iso, delta, shown in result["shifts"]:
            y, m, d = (int(part) for part in iso.split("-"))
            jy, jm, _ = jalali.to_jalali(datetime.date(y, m, d))
            total = jy * 12 + (jm - 1) + delta
            expected = jalali.from_jalali(total // 12, total % 12 + 1, 1)
            self.assertEqual(shown, expected.strftime("%a %b %d %Y"), (iso, delta))
