"""Render a stored amount the way every screen in the product renders it.

The served pages group thousands in JavaScript (`money()` in `kariz-app.js`).
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

# U+060C ARABIC COMMA — the separator `kariz-app.js` already uses, so the
# printed document and the screen agree character for character.
GROUP_SEPARATOR = "،"


@register.filter(name="money")
def money(value):
    """`12500000.00` → `12،500،000.00`; a missing amount → `—`."""
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
    grouped = ""
    for index, digit in enumerate(reversed(whole)):
        if index and index % 3 == 0:
            grouped = GROUP_SEPARATOR + grouped
        grouped = digit + grouped
    body = f"{grouped}.{fraction}" if fraction else grouped
    # U+200F keeps the minus sign attached to the number inside RTL text.
    return f"‏-{body}" if negative else body
