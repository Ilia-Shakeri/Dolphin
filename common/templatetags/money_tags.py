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

from common.jalali import to_persian_digits


register = template.Library()

# U+060C ARABIC COMMA — the separator `dolphin-app.js` already uses, so the
# printed document and the screen agree character for character.
GROUP_SEPARATOR = "،"

#: Every amount in the product is *stored* in rial. Which of the two units it
#: is *shown* in is the reader's own choice since 2.8.0
#: (`common.preferences`), and naming whichever one it is beside the figure
#: removes the only question a bare number leaves.
CURRENCY_LABEL = "ریال"
TOMAN_LABEL = "تومان"

#: Ten. Spelled out here rather than inline for the same reason
#: `common.preferences.RIALS_PER_TOMAN` is: a reader of either site can see
#: at a glance which way the conversion goes.
RIALS_PER_TOMAN = 10


def _to_toman(whole, fraction):
    """A rial digit string as a toman digit string, exactly — by moving the
    decimal point one place, never by dividing.

    `int()` on a rial total would be lossy above 2^53 in the JavaScript that
    has to agree with this, and `Decimal` here would still need the same
    string surgery to keep the fraction the caller typed. Moving the point
    is the operation both sides can perform identically.
    """
    if len(whole) > 1:
        moved_whole, moved_fraction = whole[:-1], whole[-1:]
    else:
        moved_whole, moved_fraction = "0", whole
    return moved_whole, moved_fraction + fraction


@register.filter(name="money")
def money(value, unit="rial"):
    """`12500000.00` -> `12،500،000 ریال`; a missing amount -> the em dash.

    `unit` is the reader's own `panel_currency_unit` (see
    `common.context_processors.panel_preferences`), passed explicitly by the
    template because a filter cannot see the context. `rial` is the default
    so a caller that has no reader — a management command, a test — keeps
    the behaviour this filter had before the preference existed.

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
    # The unit is applied before the ceiling below, not after: rounding a
    # rial figure up and *then* dividing would report a tenth of a rial more
    # than is owed, which is the direction the round-up rule exists to avoid
    # on the other side.
    label = CURRENCY_LABEL
    if unit == "toman":
        whole, fraction = _to_toman(whole, fraction)
        label = TOMAN_LABEL
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
    # Persian digits, same as `jalali_tags.py` already renders every date on
    # this same printed document — `dolphin-app.js`'s `money()` matches this
    # since 1.7.14 (found missing in the 1.7.13 debug sweep: a rial figure
    # was the one place on screen still reading in Latin numerals next to
    # Jalali dates and counts). Converted last, after grouping and the sign,
    # so the digit-walk above still reasons in plain Latin digits throughout.
    return to_persian_digits(f"{body} {label}")
