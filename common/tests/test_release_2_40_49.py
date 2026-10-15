"""2.40.49 — every date Jalali, the Gregorian day beside it on request (BIZ-007).

Owner decision 2026-10-14: «همه تاریخ‌ها باید شمسی باشد. در شخصی‌سازی کاربر
باید بتواند تاریخ میلادی هم اضافه کند». A personal display choice: entry,
storage, exports and printed documents stay Jalali; a Gregorian date is always
written with its month's name so it can never be read as a Jalali one.
"""

import re
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from accounts.models import User
from common.jalali import format_gregorian
from common.models import UserPreference

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "common" / "static" / "common" / "js"
TEMPLATES = [*(ROOT / "common" / "templates").rglob("*.html"), *(ROOT / "common" / "templates").rglob("*.inc"),
             *(ROOT / "profiles" / "templates").rglob("*.html"), *(ROOT / "profiles" / "templates").rglob("*.inc")]


class PreferenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cal.user", password="Strong-pass-749!", role=User.Role.SALES_MANAGER)

    def test_the_choice_is_saved_and_reaches_every_page(self):
        client = APIClient()
        client.force_authenticate(self.user)
        current = client.get("/api/v1/preferences/").json()
        self.assertEqual(current["calendar_display"], "jalali")
        self.assertEqual([option["value"] for option in current["catalog"]["calendar_displays"]], ["jalali", "jalali_gregorian"])
        saved = client.post("/api/v1/preferences/", {"calendar_display": "jalali_gregorian"}, format="json")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(UserPreference.objects.get(pk=self.user.pk).calendar_display, "jalali_gregorian")
        self.assertEqual(client.post("/api/v1/preferences/", {"calendar_display": "gregorian"}, format="json").status_code, 400)
        self.client.force_login(self.user)
        self.assertContains(self.client.get("/customers/"), 'data-calendar="jalali_gregorian"')
        self.assertContains(self.client.get("/settings/"), 'data-segmented-for="preference-calendar-display"')


class FormattingTests(SimpleTestCase):
    def test_gregorian_is_named_never_numbered(self):
        moment = datetime(2026, 10, 15, 8, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(format_gregorian(moment), "۱۵ اکتبر ۲۰۲۶")
        self.assertEqual(format_gregorian(None), "")

    def test_server_rendered_dates_follow_the_choice(self):
        moment = datetime(2026, 10, 15, 8, 0, tzinfo=dt_timezone.utc)
        template = Template('{% load jalali_tags %}{% panel_date value "datetime" %}')
        plain = template.render(Context({"value": moment}))
        both = template.render(Context({"value": moment, "panel_calendar_display": "jalali_gregorian"}))
        self.assertEqual(plain, "۱۴۰۵/۰۷/۲۳ ۱۱:۳۰")
        self.assertEqual(both, "۱۴۰۵/۰۷/۲۳ ۱۱:۳۰ (۱۵ اکتبر ۲۰۲۶)")

    def test_the_script_adds_gregorian_only_on_request_and_never_inside_a_field(self):
        source = (JS / "core" / "jalali.js").read_text(encoding="utf-8")
        self.assertIn("export function displayDay(value, {gregorian = SHOWS_GREGORIAN} = {})", source)
        self.assertIn("export function displayDate(value, {gregorian = SHOWS_GREGORIAN} = {})", source)
        self.assertIn('"اکتبر"', source)
        config = (JS / "core" / "config.js").read_text(encoding="utf-8")
        self.assertIn('document.body?.dataset.calendar === "jalali_gregorian"', config)
        # Text that fills a field someone may edit and save stays plain Jalali.
        for path in JS.rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"\.value = [^;\n]*\bdisplayDa(?:y|te)\(([^)]*)\)", text):
                with self.subTest(path=path.name, call=match.group(0)[:60]):
                    self.assertIn("gregorian: false", match.group(0))

    def test_nothing_shows_a_gregorian_date_by_itself(self):
        for path in TEMPLATES:
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"\|date:([\"'])(.*?)\1", text):
                with self.subTest(template=path.name):
                    self.assertEqual(match.group(2), "U", "a Django `date` filter would print a Gregorian date")
        for path in JS.rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"toLocale(?:Date|Time)?String\(([^)]*)\)", text):
                with self.subTest(script=path.name, call=match.group(0)):
                    self.assertIn("fa-IR", match.group(1))
        # Printed documents stay Jalali whatever the reader chose.
        printed = (ROOT / "common" / "templates" / "common" / "invoices" / "print.html").read_text(encoding="utf-8")
        self.assertNotIn("panel_date", printed)
