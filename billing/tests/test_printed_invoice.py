"""بند ۹ — the printed official invoice.

The product owner supplied a real invoice (`kala-1.pdf`) as the answer to بند
۹.۱, and it prints tax on **every line**. The stored document has no such
column: tax is one header figure computed on the discounted subtotal, which is
the only form that can be checked against `total_amount`.

So the columns are derived for print, and the rule that matters is the one
pinned here — **they must add up to what is stored**. A tax document whose
column sums disagree with its own footer is worse than one with no columns.
"""

from decimal import Decimal

from django.test import SimpleTestCase

from billing.money import printed_line_breakdown, quantize_money
from billing.words import amount_in_words


class Line:
    """The two attributes `printed_line_breakdown` reads off an invoice item."""

    def __init__(self, line_total, discount_amount="0.00"):
        self.line_total = Decimal(line_total)
        self.discount_amount = Decimal(discount_amount)


class PrintedLineBreakdownTests(SimpleTestCase):
    def rows(self, items, *, header_discount="0.00", tax_rate="0", tax_amount="0.00"):
        return printed_line_breakdown(
            items=items,
            header_discount=Decimal(header_discount),
            tax_rate=Decimal(tax_rate),
            tax_amount=Decimal(tax_amount),
        )

    def test_the_sample_invoice_reproduces(self):
        """The figures from `kala-1.pdf`: 10% on each of two lines."""
        rows = self.rows(
            [Line("34000000.00"), Line("58400000.00")],
            tax_rate="10",
            tax_amount="9240000.00",
        )
        self.assertEqual(rows[0]["net"], Decimal("34000000.00"))
        self.assertEqual(rows[0]["tax"], Decimal("3400000.00"))
        self.assertEqual(rows[0]["total"], Decimal("37400000.00"))
        self.assertEqual(rows[1]["net"], Decimal("58400000.00"))
        self.assertEqual(rows[1]["tax"], Decimal("5840000.00"))
        self.assertEqual(rows[1]["total"], Decimal("64240000.00"))

    def test_the_tax_column_totals_the_stored_tax_exactly(self):
        """Even where the proportional split does not divide evenly.

        Three equal lines and a tax of 10.00 gives 3.333… each. Whatever the
        rounding does per line, the column has to come to 10.00.
        """
        stored_tax = Decimal("10.00")
        rows = self.rows(
            [Line("100.00"), Line("100.00"), Line("100.00")],
            tax_rate="3.3333",
            tax_amount=str(stored_tax),
        )
        self.assertEqual(sum(row["tax"] for row in rows), stored_tax)

    def test_the_discount_column_totals_both_discounts_exactly(self):
        rows = self.rows(
            [Line("100.00", "5.00"), Line("200.00", "0.00"), Line("300.00", "1.00")],
            header_discount="10.00",
        )
        # Each line's own discount plus its share of the header discount.
        self.assertEqual(sum(row["discount"] for row in rows), Decimal("16.00"))

    def test_a_header_discount_that_does_not_divide_evenly_still_totals(self):
        stored_discount = Decimal("10.00")
        rows = self.rows(
            [Line("100.00"), Line("100.00"), Line("100.00")],
            header_discount=str(stored_discount),
        )
        spread = sum(row["discount"] for row in rows)
        self.assertEqual(spread, stored_discount)

    def test_the_last_line_absorbs_the_drift_and_not_more(self):
        rows = self.rows(
            [Line("100.00"), Line("100.00"), Line("100.00")],
            tax_rate="3.3333",
            tax_amount="10.00",
        )
        # An even split would be 3.33 each; the last line carries the remainder.
        self.assertEqual(rows[0]["tax"], Decimal("3.33"))
        self.assertEqual(rows[1]["tax"], Decimal("3.33"))
        self.assertEqual(rows[2]["tax"], Decimal("3.34"))

    def test_the_grand_total_column_equals_net_plus_tax_on_every_line(self):
        rows = self.rows(
            [Line("100.00"), Line("250.50")], tax_rate="9", tax_amount="31.55"
        )
        for row in rows:
            self.assertEqual(row["total"], quantize_money(row["net"] + row["tax"]))

    def test_a_document_with_no_tax_prints_zero_not_a_blank(self):
        rows = self.rows([Line("100.00")])
        self.assertEqual(rows[0]["tax"], Decimal("0.00"))
        self.assertEqual(rows[0]["total"], Decimal("100.00"))

    def test_no_lines_produces_no_rows(self):
        self.assertEqual(self.rows([]), [])


class AmountInWordsTests(SimpleTestCase):
    """بند ۹.۲ — «آیا مبلغ باید به حروف هم نوشته شود؟» «بله، به ریال»."""

    def test_the_sample_invoice_figures(self):
        self.assertEqual(
            amount_in_words(Decimal("37400000")),
            "سی و هفت میلیون و چهارصد هزار ریال",
        )
        self.assertEqual(
            amount_in_words(Decimal("64240000")),
            "شصت و چهار میلیون و دویست و چهل هزار ریال",
        )

    def test_the_teens_are_not_built_from_ten_and_a_digit(self):
        """«یازده», not «ده و یک»."""
        self.assertEqual(amount_in_words(Decimal("11")), "یازده ریال")
        self.assertEqual(amount_in_words(Decimal("19")), "نوزده ریال")
        self.assertEqual(amount_in_words(Decimal("21")), "بیست و یک ریال")

    def test_zero_is_written_out_rather_than_left_empty(self):
        self.assertEqual(amount_in_words(Decimal("0")), "صفر ریال")

    def test_a_missing_amount_is_never_mangled(self):
        self.assertEqual(amount_in_words(None), "—")
        self.assertEqual(amount_in_words("not-a-number"), "—")

    def test_the_fraction_rounds_up_exactly_as_the_digits_do(self):
        """The two renderings of one amount must not disagree by a rial."""
        self.assertEqual(amount_in_words(Decimal("10.01")), "یازده ریال")
        self.assertEqual(amount_in_words(Decimal("10.00")), "ده ریال")

    def test_a_negative_amount_says_so_in_a_word(self):
        """A minus sign is easy to miss and easy to add."""
        self.assertTrue(amount_in_words(Decimal("-2500.40")).startswith("منفی "))

    def test_an_amount_too_large_to_write_is_refused_not_truncated(self):
        with self.assertRaises(ValueError):
            amount_in_words(Decimal("1000000000000"))
