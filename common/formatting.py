"""Persian digits and grouped amounts, in one place on the Python side.

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

Since 2.8.0 every amount can be shown in rial or in toman, per reader
(`common/preferences.py`). What is *stored* never changes: rial, always. The
unit reaches this module as an argument rather than being looked up here,
because these functions are called in a loop while composing a payload and
the reader is already known one level up.
"""

from decimal import ROUND_CEILING, Decimal

#: U+060C, the Arabic comma — the separator every amount in this product uses.
GROUP_SEPARATOR = "،"
CURRENCY_LABEL = "ریال"
TOMAN_LABEL = "تومان"
RIALS_PER_TOMAN = Decimal(10)

_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def persian_digits(value):
    return str(value).translate(_PERSIAN)


def money(amount, unit="rial"):
    """A stored rial amount, grouped, in Persian digits, in the reader's unit.

    Matches the panel's own `money()` in `dolphin-app.js` character for
    character, including the ceiling: the product owner's rule is that a
    figure shown to a customer must never read lower than what is owed. In
    toman that ceiling costs at most one toman of overstatement, the same
    trade already accepted for the rial.

    The fraction is dropped because neither unit has a sub-unit in daily
    use, and the grouping walks the integer string rather than a float, so a
    stored amount can never be moved by a round trip.
    """
    value = Decimal(amount or 0)
    if unit == "toman":
        value = value / RIALS_PER_TOMAN
        label = TOMAN_LABEL
    else:
        label = CURRENCY_LABEL
    negative = value < 0
    # The ceiling is applied to the magnitude, not to the signed value, so
    # `-12.5` reads as `-13` and not `-12`: the two other formatters in this
    # product (`money_tags.money`, `money()` in dolphin-app.js) both strip
    # the sign before rounding, and the three have to agree to the last
    # digit or a printed document and the screen it was checked against
    # would not.
    whole = int(abs(value).quantize(Decimal("1"), rounding=ROUND_CEILING))
    grouped = f"{whole:,}".replace(",", GROUP_SEPARATOR)
    return persian_digits(f"{'‏-' if negative else ''}{grouped} {label}")
