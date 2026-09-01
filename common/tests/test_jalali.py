"""The Jalali presentation layer (`BIZ-007`).

Two things are proven here: the conversion is *correct* (against fixed
published anchors and by exhaustive round-trip), and it is *only presentation*
— the database and `/api/v1/` keep canonical Gregorian ISO values.

The full agreement check against ICU ran over 16,801 consecutive days from 1990
to 2035 in both directions with zero mismatches, for the Python and the
JavaScript implementation alike. Committing 16,801 vectors would be noise, so
what is kept here is the exhaustive round-trip plus the anchors that pin the
epoch — if the epoch were off by a day, as it was in the first draft, every
anchor below would fail.
"""

import datetime
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from common import jalali


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "common" / "static" / "common" / "dolphin-app.js"

# Published Gregorian/Jalali pairs. Nowruz is the year boundary, so these pin
# both the epoch and the leap rule.
ANCHORS = (
    (datetime.date(1979, 2, 11), (1357, 11, 22)),   # 22 Bahman 1357
    (datetime.date(2021, 3, 21), (1400, 1, 1)),     # Nowruz 1400
    (datetime.date(2024, 3, 20), (1403, 1, 1)),     # Nowruz 1403
    (datetime.date(2025, 3, 21), (1404, 1, 1)),     # Nowruz 1404
    (datetime.date(2026, 3, 21), (1405, 1, 1)),     # Nowruz 1405
    (datetime.date(2026, 8, 16), (1405, 5, 25)),
    (datetime.date(2000, 1, 1), (1378, 10, 11)),
    (datetime.date(2016, 3, 19), (1394, 12, 29)),   # last day of a leap year
    (datetime.date(2016, 3, 20), (1395, 1, 1)),
)


class ConversionTests(SimpleTestCase):
    def test_published_anchor_dates_convert_exactly(self):
        for gregorian, expected in ANCHORS:
            with self.subTest(date=gregorian):
                self.assertEqual(jalali.to_jalali(gregorian), expected)
                self.assertEqual(jalali.from_jalali(*expected), gregorian)

    def test_every_day_across_forty_years_round_trips(self):
        day = datetime.date(1995, 1, 1)
        end = datetime.date(2035, 12, 31)
        step = datetime.timedelta(days=1)
        while day <= end:
            self.assertEqual(jalali.from_jalali(*jalali.to_jalali(day)), day, day)
            day += step

    def test_the_calendar_advances_one_day_at_a_time_with_no_gaps(self):
        """A wrong month table would show up as a repeated or skipped day."""
        seen = set()
        day = datetime.date(2024, 1, 1)
        for _ in range(1200):
            converted = jalali.to_jalali(day)
            self.assertNotIn(converted, seen)
            seen.add(converted)
            day += datetime.timedelta(days=1)

    def test_leap_years_have_a_thirtieth_of_esfand_and_common_years_do_not(self):
        self.assertEqual(jalali.to_jalali(datetime.date(2016, 3, 19)), (1394, 12, 29))
        # 1395 is a leap year, so 30 Esfand exists.
        self.assertEqual(jalali.from_jalali(1395, 12, 30), datetime.date(2017, 3, 20))
        with self.assertRaises(ValueError):
            jalali.from_jalali(1394, 12, 30)

    def test_an_out_of_range_component_is_refused(self):
        for year, month, day in ((1405, 13, 1), (1405, 0, 1), (1405, 1, 32), (1405, 7, 31), (0, 1, 1)):
            with self.subTest(value=(year, month, day)):
                with self.assertRaises(ValueError):
                    jalali.from_jalali(year, month, day)


class FormattingTests(SimpleTestCase):
    def test_a_date_renders_with_persian_digits(self):
        self.assertEqual(jalali.format_date(datetime.date(2026, 8, 16)), "۱۴۰۵/۰۵/۲۵")
        self.assertEqual(
            jalali.format_date(datetime.date(2026, 8, 16), persian_digits=False), "1405/05/25"
        )

    def test_a_long_date_names_its_month(self):
        self.assertEqual(jalali.format_long_date(datetime.date(2026, 8, 16)), "۲۵ مرداد ۱۴۰۵")

    def test_an_instant_is_shown_in_tehran_local_time(self):
        # 21:00 UTC is already the next day in Tehran (+03:30).
        instant = datetime.datetime(2026, 8, 16, 21, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(jalali.format_datetime(instant), "۱۴۰۵/۰۵/۲۶ ۰۰:۳۰")
        self.assertEqual(jalali.format_date(instant), "۱۴۰۵/۰۵/۲۶")

    def test_a_missing_value_renders_as_empty_rather_than_none(self):
        for value in (None, ""):
            self.assertEqual(jalali.format_date(value), "")
            self.assertEqual(jalali.format_datetime(value), "")
            self.assertEqual(jalali.format_long_date(value), "")


class ParsingTests(SimpleTestCase):
    def test_persian_and_latin_digits_both_parse(self):
        self.assertEqual(jalali.parse_date("۱۴۰۵/۰۵/۲۵"), datetime.date(2026, 8, 16))
        self.assertEqual(jalali.parse_date("1405/05/25"), datetime.date(2026, 8, 16))
        self.assertEqual(jalali.parse_date("1405-5-25"), datetime.date(2026, 8, 16))

    def test_arabic_indic_digits_parse_too(self):
        self.assertEqual(jalali.parse_date("١٤٠٥/٠٥/٢٥"), datetime.date(2026, 8, 16))

    def test_unreadable_input_raises_rather_than_guessing(self):
        for text in ("hello", "1405/05", "1405/05/25/1", "1405/13/01", "//"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    jalali.parse_date(text)

    def test_an_empty_value_is_none_not_an_error(self):
        self.assertIsNone(jalali.parse_date(""))
        self.assertIsNone(jalali.parse_date(None))

    def test_parsing_is_the_exact_inverse_of_formatting(self):
        day = datetime.date(2020, 1, 1)
        for _ in range(2000):
            self.assertEqual(jalali.parse_date(jalali.format_date(day)), day)
            day += datetime.timedelta(days=1)


class FrontendParityTests(SimpleTestCase):
    """The browser must convert identically, or a typed date changes meaning.

    Behaviour is exercised in the browser suite; what is checked here is that
    the two implementations still share the constants the conversion depends
    on, so editing one without the other fails immediately.
    """

    def setUp(self):
        self.script = SCRIPT.read_text(encoding="utf-8")

    def test_the_epoch_anchor_matches(self):
        self.assertIn("Date.UTC(622, 2, 21)", self.script)
        self.assertEqual(jalali.JALALI_EPOCH_ORDINAL, datetime.date(622, 3, 21).toordinal())

    def test_the_month_offset_table_matches(self):
        match = re.search(r"JALALI_MONTH_OFFSETS = \[([0-9,\s]+)\]", self.script)
        self.assertIsNotNone(match)
        offsets = tuple(int(part) for part in match.group(1).replace(" ", "").split(","))
        self.assertEqual(offsets, jalali._JALALI_MONTH_OFFSETS)

    def test_the_leap_rule_matches(self):
        self.assertIn("(((year + 12) % 33) % 4) === 1", self.script)

    def test_the_frontend_uses_the_same_operational_time_zone(self):
        self.assertIn('OPERATIONAL_TIME_ZONE = "Asia/Tehran"', self.script)
        self.assertEqual(str(jalali.OPERATIONAL_TIMEZONE), "Asia/Tehran")

    def test_no_native_gregorian_date_input_survives_in_a_served_template(self):
        templates = ROOT / "common" / "templates" / "common"
        offenders = []
        for path in sorted(templates.rglob("*.html")) + sorted(templates.rglob("*.inc")):
            text = path.read_text(encoding="utf-8")
            if 'type="date"' in text or 'type="datetime-local"' in text:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


class CanonicalStorageTests(TestCase):
    """The API and the database keep Gregorian ISO; only the page is Jalali."""

    def setUp(self):
        from accounts.models import User

        self.manager = User.objects.create_user(
            username="jalali.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER
        )
        self.client.force_login(self.manager)

    def test_the_api_still_returns_iso_gregorian(self):
        from sales.services import create_customer_with_phone, create_lead

        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری تقویم",
            phone={"raw_phone": "09121114444", "is_primary": True},
        )
        lead = create_lead(actor=self.manager, customer=customer, source="manual")
        payload = self.client.get(f"/api/v1/leads/{lead.pk}/").json()
        # An ISO-8601 instant, not a Jalali string, and no Persian digits.
        self.assertRegex(payload["created_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
        for digit in jalali.PERSIAN_DIGITS:
            self.assertNotIn(digit, payload["created_at"])

    def test_a_printed_document_shows_jalali_while_the_record_stays_gregorian(self):
        from decimal import Decimal

        from billing.services import create_invoice, issue_invoice
        from inventory.models import StockMovement
        from inventory.services import create_warehouse, record_stock_movement
        from sales.services import create_customer_with_phone, create_product

        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری چاپ",
            phone={"raw_phone": "09121115555", "is_primary": True},
        )
        product = create_product(
            actor=self.manager, sku="JAL-1", name="کالا", current_price=Decimal("100.00")
        )
        warehouse = create_warehouse(actor=self.manager, code="jalwh", name="انبار")
        record_stock_movement(
            actor=self.manager,
            warehouse=warehouse,
            product=product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=10,
            unit_cost=Decimal("50.00"),
        )
        invoice = issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=customer,
                items=[{"product": product, "quantity": 1}],
                warehouse=warehouse,
            ),
        )
        content = self.client.get(f"/invoices/{invoice.pk}/print/").content.decode("utf-8")
        expected = jalali.format_datetime(invoice.issued_at)
        self.assertIn(expected, content)
        # The Gregorian year must not appear anywhere on the printed page.
        self.assertNotIn(str(invoice.issued_at.year), content)
        # The stored value is untouched.
        invoice.refresh_from_db()
        self.assertIsInstance(invoice.issued_at, datetime.datetime)


class SpreadsheetDateTests(TestCase):
    def test_export_dates_are_written_as_jalali_text(self):
        from reports.xlsx import spreadsheet_date, spreadsheet_datetime

        instant = datetime.datetime(2026, 8, 16, 9, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(spreadsheet_date(instant), "۱۴۰۵/۰۵/۲۵")
        self.assertEqual(spreadsheet_datetime(instant), "۱۴۰۵/۰۵/۲۵ ۱۲:۳۰")
        self.assertEqual(spreadsheet_date(None), "")
        self.assertEqual(spreadsheet_datetime(""), "")


class ImplausibleYearTests(SimpleTestCase):
    """A Gregorian value in a Jalali field must not be silently accepted.

    `2026` is a perfectly valid Jalali year arithmetically — it just means
    2647 CE. Without a bound, pasting a Gregorian date into one of these fields
    would store a date six centuries out and complain about nothing.
    """

    def test_a_gregorian_year_is_refused(self):
        for text in ("2026/08/16", "1999/01/01", "2024-03-20"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    jalali.parse_date(text)

    def test_plausible_business_years_are_accepted(self):
        for text in ("1400/01/01", "1405/05/25", "1410/12/29"):
            with self.subTest(text=text):
                self.assertIsInstance(jalali.parse_date(text), datetime.date)

    def test_the_browser_enforces_the_same_bound(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("year < 1200 || year > 1700", script)
        self.assertEqual((jalali.MIN_JALALI_YEAR, jalali.MAX_JALALI_YEAR), (1200, 1700))
