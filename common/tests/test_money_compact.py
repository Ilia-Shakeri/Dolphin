"""A dashboard tile shortens a large amount; the exact figure stays available (2.38.1)."""

from decimal import Decimal

from django.test import SimpleTestCase

from common import formatting


class MoneyCompactTests(SimpleTestCase):
    def test_below_a_million_it_is_the_full_figure(self):
        self.assertEqual(formatting.money_compact(Decimal("999999"), "rial"), formatting.money(Decimal("999999"), "rial"))

    def test_large_amounts_use_a_step_and_never_read_lower_than_the_truth(self):
        self.assertEqual(formatting.money_compact(Decimal("1250000000"), "rial"), "۱٫۲۵ میلیارد ریال")
        # 1,234,567,891 rial is 1.2345… billion: rounded up to 1.24, never down to 1.23.
        self.assertEqual(formatting.money_compact(Decimal("1234567891"), "rial"), "۱٫۲۴ میلیارد ریال")
        self.assertEqual(formatting.money_compact(Decimal("3000000"), "rial"), "۳ میلیون ریال")
        self.assertEqual(formatting.money_compact(Decimal("2500000000000"), "rial"), "۲٫۵ هزار میلیارد ریال")

    def test_it_follows_the_readers_unit(self):
        self.assertEqual(formatting.money_compact(Decimal("12500000000"), "toman"), "۱٫۲۵ میلیارد تومان")

    def test_a_negative_amount_keeps_its_sign(self):
        self.assertTrue(formatting.money_compact(Decimal("-5000000"), "rial").startswith("‏-"))
