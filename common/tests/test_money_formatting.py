"""The printed document must show an amount the way the screens show it."""

import pathlib
import re
from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase

from common.templatetags.money_tags import money


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
APP_JS = REPOSITORY_ROOT / "common" / "static" / "common" / "forooshbin-app.js"
PRINT_TEMPLATES = (
    REPOSITORY_ROOT / "common" / "templates" / "common" / "invoices" / "print.html",
)


class MoneyFilterTests(SimpleTestCase):
    def test_thousands_are_grouped_the_way_the_screens_group_them(self):
        self.assertEqual(money(Decimal("12500000.00")), "12،500،000.00")
        self.assertEqual(money("12500000.00"), "12،500،000.00")
        self.assertEqual(money(Decimal("0.00")), "0.00")
        self.assertEqual(money(Decimal("999.99")), "999.99")
        self.assertEqual(money(Decimal("1000")), "1،000")
        self.assertEqual(money(Decimal("123456789012.34")), "123،456،789،012.34")

    def test_a_missing_or_unrecognised_amount_is_never_mangled(self):
        self.assertEqual(money(None), "—")
        self.assertEqual(money(""), "—")
        self.assertEqual(money("—"), "—")
        self.assertEqual(money("not-a-number"), "not-a-number")

    def test_a_negative_amount_keeps_its_sign_beside_the_number(self):
        rendered = money(Decimal("-2500.50"))
        self.assertTrue(rendered.endswith("-2،500.50"))
        self.assertEqual(rendered[0], "‏")

    def test_the_last_digit_of_a_large_total_survives_formatting(self):
        # Going through float would round this; the amount is authoritative.
        self.assertEqual(money(Decimal("9007199254740993.01")), "9،007،199،254،740،993.01")

    def test_the_filter_is_loadable_from_a_template(self):
        rendered = Template(
            "{% load money_tags %}{{ amount|money }}"
        ).render(Context({"amount": Decimal("450000.00")}))
        self.assertEqual(rendered, "450،000.00")

    def test_the_separator_matches_the_one_the_application_javascript_uses(self):
        source = APP_JS.read_text(encoding="utf-8")
        grouping = re.search(r'whole\.replace\(/\\B\(\?=\(\\d\{3\}\)\+\(\?!\\d\)\)/g, "(.)"\)', source)
        self.assertIsNotNone(grouping, "forooshbin-app.js no longer groups thousands as expected")
        self.assertEqual(grouping.group(1), "،")

    def test_every_printed_amount_goes_through_the_filter(self):
        amount_field = re.compile(
            r"\{\{\s*[\w.]*(?:amount|price|total|balance_due)\w*\s*(\|[^}]*)?\}\}"
        )
        for path in PRINT_TEMPLATES:
            source = path.read_text(encoding="utf-8")
            with self.subTest(template=path.name):
                self.assertIn("{% load jalali_tags money_tags %}", source)
                for match in amount_field.finditer(source):
                    self.assertIn(
                        "money",
                        match.group(0),
                        f"{path.name}: {match.group(0)} is printed without grouping",
                    )
