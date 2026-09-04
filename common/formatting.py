"""Persian digits and grouped rial, in one place on the Python side.

`reports/list_charts.py` grew these first, because a chart's slice labels are
built server-side and had to match what `money()` in
`common/templatetags/money_tags.py` prints on the page beside them. The
dashboard now composes the same kind of already-formatted figure, so rather
than a third copy the two helpers live here and `list_charts` reads them
from here — the same move `common/labels.py` made for the Persian words in
1.8.3.

The template filter stays where it is on purpose: it answers a different
question (an amount inside a rendered page, with its own `—` for a missing
value and its own round-up rule), and merging the two would make one of them
lie about what it does.
"""

from decimal import Decimal

#: U+060C, the Arabic comma — the separator every amount in this product uses.
GROUP_SEPARATOR = "،"
CURRENCY_LABEL = "ریال"

_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def persian_digits(value):
    return str(value).translate(_PERSIAN)


def money(amount):
    """Grouped rial in Persian digits, matching the panel's own `money()`.

    The fraction is dropped because rial has no sub-unit in daily use, and
    the grouping walks the integer string rather than a float, so a stored
    amount can never be moved by a round trip.
    """
    whole = int(Decimal(amount or 0).quantize(Decimal("1")))
    negative = whole < 0
    grouped = f"{abs(whole):,}".replace(",", GROUP_SEPARATOR)
    return persian_digits(f"{'‏-' if negative else ''}{grouped} {CURRENCY_LABEL}")
