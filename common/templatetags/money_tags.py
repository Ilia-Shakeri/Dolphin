"""Render a stored amount the way every screen in the product renders it.

The served pages group thousands in JavaScript (`money()` in `dolphin-app.js`).
The print and PDF documents are rendered by Django and had no equivalent, so a
printed invoice showed `12500000.00` where the same amount on screen showed
`12،500،000.00`. On a rial total that is not cosmetic: an unseparated eight-digit
figure is exactly the kind a reader mis-scans by a factor of ten.

Grouping walks the string instead of going through `float`, for the same reason
the JavaScript does: the amount is authoritative as stored, and a float
round-trip could move its last digit.
"""

from decimal import Decimal

from django import template


register = template.Library()

# U+060C ARABIC COMMA — the separator `dolphin-app.js` already uses, so the
# printed document and the screen agree character for character.
GROUP_SEPARATOR = "،"

#: Every amount in the product is rial. Naming it beside the figure removes the
#: only question a bare number leaves.
CURRENCY_LABEL = "ریال"


@register.filter(name="money")
def money(value):
    """`12500000.00` -> `12،500،000 ریال`; a missing amount -> the em dash.

    Rial has no sub-unit in daily use, so the fraction is dropped rather than
    printed as a permanent `.00`. It is dropped by **rounding up** on the digit
    string — never through `float`, for the same reason the grouping walks the
    string: the amount is authoritative as stored and a float round-trip could
    move its last digit.

    Rounding up rather than half-up is the product owner's rule: a figure shown
    to a customer must not be lower than what is owed. The cost is at most one
    rial of overstatement. The stored value keeps its two decimals untouched —
    this is display only.
    """
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        # A float never carries an authoritative amount here; formatting one
        # would quietly certify a rounding error. Decimals and strings only.
        value = Decimal(repr(value))
    text = str(value).strip()
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    whole, _, fraction = text.partition(".")
    if not whole.isdigit():
        # Not a number we recognise; show it unchanged rather than mangling it.
        return str(value)
    # Ceiling, matching `money()` in dolphin-app.js: any fraction at all
    # rounds up. A printed document and the screen it was checked against must
    # agree to the rial, so both use the same rule and neither may drift.
    if fraction and any(digit in "123456789" for digit in fraction):
        whole = str(int(whole) + 1)
    grouped = ""
    for index, digit in enumerate(reversed(whole)):
        if index and index % 3 == 0:
            grouped = GROUP_SEPARATOR + grouped
        grouped = digit + grouped
    # U+200F keeps the minus sign attached to the number inside RTL text.
    body = f"‏-{grouped}" if negative and grouped != "0" else grouped
    return f"{body} {CURRENCY_LABEL}"
