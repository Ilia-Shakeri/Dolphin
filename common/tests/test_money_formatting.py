"""The printed document must show an amount the way the screens show it.

Since 1.1.0 that means three things together: thousands grouped with the Arabic
comma, no fraction, and the word ریال beside the figure. The rial has no
sub-unit in daily use, so a permanent `٫۰۰` only made an already long number
longer; and an eight-digit figure with no currency word beside it is exactly the
kind a reader mis-scans by a factor of ten.
"""

import pathlib
import re
from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase

from common.jalali import to_persian_digits
from common.templatetags.money_tags import money


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
APP_JS = REPOSITORY_ROOT / "common" / "static" / "common" / "dolphin-app.js"
PRINT_TEMPLATES = (
    REPOSITORY_ROOT / "common" / "templates" / "common" / "invoices" / "print.html",
)


class MoneyFilterTests(SimpleTestCase):
    def test_thousands_are_grouped_and_the_currency_is_named(self):
        self.assertEqual(money(Decimal("12500000.00")), "۱۲،۵۰۰،۰۰۰ ریال")
        self.assertEqual(money("12500000.00"), "۱۲،۵۰۰،۰۰۰ ریال")
        self.assertEqual(money(Decimal("0.00")), "۰ ریال")
        self.assertEqual(money(Decimal("1000")), "۱،۰۰۰ ریال")
        self.assertEqual(money(Decimal("123456789012.34")), "۱۲۳،۴۵۶،۷۸۹،۰۱۳ ریال")

    def test_any_fraction_at_all_rounds_the_figure_up(self):
        """Ceiling, not half-up — the product owner's rule since 1.3.0.

        A figure shown to a customer must never be lower than what is actually
        owed. Half-up satisfied that for `.5` and above and quietly broke it
        below: `999.49` used to print as `999`, understating the debt. Rounding
        up can overstate by at most one rial, and that is the direction chosen.
        """
        self.assertEqual(money(Decimal("999.99")), "۱،۰۰۰ ریال")
        self.assertEqual(money(Decimal("999.50")), "۱،۰۰۰ ریال")
        self.assertEqual(money(Decimal("999.49")), "۱،۰۰۰ ریال")
        self.assertEqual(money(Decimal("999.01")), "۱،۰۰۰ ریال")
        # A whole amount must not be nudged upward — only a real fraction is.
        self.assertEqual(money(Decimal("999.00")), "۹۹۹ ریال")
        self.assertEqual(money(Decimal("0.01")), "۱ ریال")
        # The carry has to propagate through the whole number, not just its
        # last digit.
        self.assertEqual(money(Decimal("999999.60")), "۱،۰۰۰،۰۰۰ ریال")

    def test_a_missing_or_unrecognised_amount_is_never_mangled(self):
        self.assertEqual(money(None), "—")
        self.assertEqual(money(""), "—")
        self.assertEqual(money("—"), "—")
        self.assertEqual(money("not-a-number"), "not-a-number")

    def test_a_negative_amount_keeps_its_sign_beside_the_number(self):
        # The magnitude rounds up, so a negative figure moves away from zero.
        rendered = money(Decimal("-2500.40"))
        self.assertTrue(rendered.startswith("‏-۲،۵۰۱"), rendered)
        self.assertTrue(rendered.endswith("ریال"))

    def test_the_last_digit_of_a_large_total_survives_formatting(self):
        # Going through float would round this away; the amount is
        # authoritative as stored. As a double, 9007199254740993.01 collapses to
        # ...992, so a float path would carry to ...993 — reaching ...994 is only
        # possible on the digit string.
        self.assertEqual(
            money(Decimal("9007199254740993.01")), "۹،۰۰۷،۱۹۹،۲۵۴،۷۴۰،۹۹۴ ریال"
        )

    def test_the_stored_amount_is_not_what_changed(self):
        """Dropping the fraction is a display decision and nothing more."""
        amount = Decimal("450000.75")
        money(amount)
        self.assertEqual(amount, Decimal("450000.75"))
        self.assertEqual(amount.as_tuple().exponent, -2)

    def test_the_filter_is_loadable_from_a_template(self):
        rendered = Template(
            "{% load money_tags %}{{ amount|money }}"
        ).render(Context({"amount": Decimal("450000.00")}))
        self.assertEqual(rendered, "۴۵۰،۰۰۰ ریال")

    def test_the_separator_matches_the_one_the_application_javascript_uses(self):
        source = APP_JS.read_text(encoding="utf-8")
        grouping = re.search(r'whole\.replace\(/\\B\(\?=\(\\d\{3\}\)\+\(\?!\\d\)\)/g, "(.)"\)', source)
        self.assertIsNotNone(grouping, "dolphin-app.js no longer groups thousands as expected")
        self.assertEqual(grouping.group(1), "،")

    def test_the_currency_word_matches_the_one_the_javascript_appends(self):
        """The printed document and the screen must agree, word for word."""
        source = APP_JS.read_text(encoding="utf-8")
        self.assertIn('`${body} ریال`', source)

    def test_the_digit_script_matches_the_one_the_javascript_produces(self):
        """Since 1.7.14: both money() implementations render Persian digits,
        the same convention every Jalali date on both surfaces already used.
        """
        source = APP_JS.read_text(encoding="utf-8")
        self.assertIn("toPersianDigits(shown)", source)
        self.assertEqual(money(Decimal("1000")), to_persian_digits("1،000 ریال"))

    def test_every_printed_amount_goes_through_the_filter(self):
        amount_field = re.compile(
            r"\{\{\s*[\w.]*(?:amount|price|total|balance_due)\w*\s*(\|[^}]*)?\}\}"
        )
        # `_in_words` is not a number. `total_in_words` arrives already rendered
        # as Persian text by `amount_in_words`, and putting it through `money`
        # would mangle it rather than group it. Narrow on purpose: every other
        # name containing "total" is still required to go through the filter.
        not_a_number = re.compile(r"_in_words\b")
        for path in PRINT_TEMPLATES:
            source = path.read_text(encoding="utf-8")
            with self.subTest(template=path.name):
                self.assertIn("{% load jalali_tags money_tags %}", source)
                for match in amount_field.finditer(source):
                    if not_a_number.search(match.group(0)):
                        continue
                    self.assertIn(
                        "money",
                        match.group(0),
                        f"{path.name}: {match.group(0)} is printed without grouping",
                    )
