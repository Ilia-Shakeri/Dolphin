"""Persian words for an amount of rial. (بند ۹.۲)

An official invoice states the amount twice — once in digits and once in
words — so that a digit cannot be added to it after signing. The product owner
asked for the words to be in **rial**, matching the figures beside them.

Nothing here is localisable and nothing here is configurable. It is Persian, it
is rial, and it is written out the way the sample invoice writes it.
"""

from decimal import Decimal


ONES = (
    "", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه",
)
TEENS = (
    "ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده",
    "هفده", "هجده", "نوزده",
)
TENS = (
    "", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود",
)
HUNDREDS = (
    "", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد",
    "هشتصد", "نهصد",
)
#: Persian uses the short scale up to میلیارد and then repeats it with هزار.
#: Three groups is 10^12 - 1, well past `MAX_MONEY`, so the table does not need
#: to go further; `amount_in_words` raises rather than printing a wrong figure
#: if it ever does.
SCALES = ("", " هزار", " میلیون", " میلیارد")

SEPARATOR = " و "


def _three_digits(value):
    """Words for 0..999, with no scale word attached."""
    parts = []
    hundreds, rest = divmod(value, 100)
    if hundreds:
        parts.append(HUNDREDS[hundreds])
    if 10 <= rest <= 19:
        parts.append(TEENS[rest - 10])
    else:
        tens, ones = divmod(rest, 10)
        if tens:
            parts.append(TENS[tens])
        if ones:
            parts.append(ONES[ones])
    return SEPARATOR.join(parts)


def amount_in_words(amount):
    """`Decimal("37400000")` -> `"سی و هفت میلیون و چهارصد هزار ریال"`.

    The fraction is dropped by rounding **up**, exactly as `money()` does on
    screen and in the printed figures. The two renderings of the same amount
    must not disagree by a rial, or the document contradicts itself — which is
    the one thing a document that states its amount twice is meant to prevent.

    Returns `"صفر ریال"` for zero, and keeps a negative sign as a word rather
    than a symbol, since a minus sign is easy to miss and easy to add.
    """
    if amount is None:
        return "—"
    try:
        value = Decimal(str(amount))
    except (ArithmeticError, ValueError):
        return "—"

    negative = value < 0
    value = abs(value)
    # Ceiling, matching the digits beside it.
    whole = int(value)
    if value != whole:
        whole += 1

    if whole == 0:
        return "صفر ریال"
    if whole >= 1000 ** len(SCALES):
        raise ValueError("Amount is too large to write out.")

    groups = []
    remaining = whole
    index = 0
    while remaining:
        remaining, group = divmod(remaining, 1000)
        if group:
            groups.append(_three_digits(group) + SCALES[index])
        index += 1

    words = SEPARATOR.join(reversed(groups))
    if negative:
        return f"منفی {words} ریال"
    return f"{words} ریال"
