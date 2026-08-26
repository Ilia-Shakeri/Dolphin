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
    """The columns must add up to the footer printed beneath them.

    Everything is whole rial, because that is what the reader sees. An earlier
    version apportioned exact decimals — the stored values summed perfectly, and
    then the page rounded each line up for display and the column came to a
    rial more than the total. Rounding up is not additive, so the arithmetic has
    to happen in the displayed units or the document contradicts itself.
    """

    def breakdown(self, items, *, header_discount="0.00", tax_rate="0", tax_amount="0.00"):
        return printed_line_breakdown(
            items=items,
            header_discount=Decimal(header_discount),
            tax_rate=Decimal(tax_rate),
            tax_amount=Decimal(tax_amount),
        )

    def assert_columns_sum_to_footer(self, rows, totals):
        for column in ("gross", "discount", "net", "tax", "total"):
            self.assertEqual(
                sum(row[column] for row in rows),
                totals[column],
                f"the {column} column does not add up to its own footer",
            )

    def test_the_sample_invoice_reproduces(self):
        """The figures from `kala-1.pdf`: 10% on each of two lines."""
        rows, totals = self.breakdown(
            [Line("34000000.00"), Line("58400000.00")],
            tax_rate="10", tax_amount="9240000.00",
        )
        self.assertEqual(rows[0]["net"], 34000000)
        self.assertEqual(rows[0]["tax"], 3400000)
        self.assertEqual(rows[0]["total"], 37400000)
        self.assertEqual(rows[1]["net"], 58400000)
        self.assertEqual(rows[1]["tax"], 5840000)
        self.assertEqual(rows[1]["total"], 64240000)
        self.assert_columns_sum_to_footer(rows, totals)

    def test_the_case_that_was_off_by_a_rial(self):
        """Two lines whose shares both ended in a fraction.

        Each was rounded up independently and the discount column came to
        5,000,001 under a footer reading 5,000,000.
        """
        rows, totals = self.breakdown(
            [Line("370000000.00"), Line("127500000.00")],
            header_discount="5000000.00", tax_rate="9", tax_amount="44325000.00",
        )
        self.assert_columns_sum_to_footer(rows, totals)
        self.assertEqual(totals["discount"], 5000000)
        self.assertEqual(totals["tax"], 44325000)
        self.assertEqual(totals["total"], 536825000)

    def test_a_tax_that_does_not_divide_evenly_still_adds_up(self):
        rows, totals = self.breakdown(
            [Line("100.00"), Line("100.00"), Line("100.00")],
            tax_rate="3.3333", tax_amount="10.00",
        )
        self.assert_columns_sum_to_footer(rows, totals)
        self.assertEqual(totals["tax"], 10)

    def test_a_discount_that_does_not_divide_evenly_still_adds_up(self):
        rows, totals = self.breakdown(
            [Line("100.00"), Line("100.00"), Line("100.00")], header_discount="10.00",
        )
        self.assert_columns_sum_to_footer(rows, totals)
        self.assertEqual(totals["discount"], 10)

    def test_a_line_discount_reaches_both_the_column_and_the_footer(self):
        rows, totals = self.breakdown(
            [Line("100.00", "5.00"), Line("200.00", "0.00"), Line("300.00", "1.00")],
            header_discount="10.00",
        )
        self.assert_columns_sum_to_footer(rows, totals)
        # Every discount on the document: the three line discounts and the header.
        self.assertEqual(totals["discount"], 16)
        # And gross is before any of them.
        self.assertEqual(totals["gross"], 606)

    def test_every_line_total_is_its_own_net_plus_tax(self):
        rows, _ = self.breakdown(
            [Line("100.00"), Line("250.50")], tax_rate="9", tax_amount="31.55",
        )
        for row in rows:
            self.assertEqual(row["total"], row["net"] + row["tax"])

    def test_nothing_printed_carries_a_fraction(self):
        """The panel shows no decimals anywhere, this document included."""
        rows, totals = self.breakdown(
            [Line("33.33"), Line("66.67")], header_discount="0.01",
            tax_rate="9", tax_amount="8.99",
        )
        for row in rows:
            for column in ("gross", "discount", "net", "tax", "total"):
                self.assertIsInstance(row[column], int)
        for value in totals.values():
            self.assertIsInstance(value, int)

    def test_a_document_with_no_tax_prints_zero_not_a_blank(self):
        rows, totals = self.breakdown([Line("100.00")])
        self.assertEqual(rows[0]["tax"], 0)
        self.assertEqual(rows[0]["total"], 100)
        self.assertEqual(totals["tax"], 0)

    def test_no_lines_produces_no_rows(self):
        rows, totals = self.breakdown([])
        self.assertEqual(rows, [])
        self.assertEqual(totals["total"], 0)

    def test_a_free_document_does_not_divide_by_its_own_zero(self):
        """Every line at zero leaves nothing to weigh the apportionment by."""
        rows, totals = self.breakdown([Line("0.00"), Line("0.00")])
        self.assert_columns_sum_to_footer(rows, totals)


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
