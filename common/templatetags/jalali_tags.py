"""Template filters that render a stored Gregorian value as Jalali.

Presentation only (`BIZ-007`). The model field, the serializer, and every
`/api/v1/` response keep the canonical Gregorian ISO value; these filters exist
so a template never has to know how the conversion works, and so there is one
place to change it.
"""

from django import template

from common import jalali


register = template.Library()


@register.filter(name="persian_digits")
def persian_digits(value):
    """`203` -> `۲۰۳`.

    Every count and every amount composed in JavaScript or in
    `common/formatting.py` already reaches the page in Persian digits; the
    handful composed straight into a template did not, and read as Latin
    numerals beside them. That went unnoticed for as long as it did because
    IRANSansWeb draws ASCII digits in a Persian-looking form — choosing any
    other face on the settings page (2.8.0) makes the difference plain.
    """
    if value is None or value == "":
        return "—"
    return jalali.to_persian_digits(str(value))


@register.filter(name="jalali")
def jalali_date(value):
    """`۱۴۰۵/۰۵/۲۵`, or an empty string for a missing value."""
    try:
        return jalali.format_date(value)
    except (ValueError, TypeError, AttributeError):
        # A template must not raise over an unexpected value; showing nothing is
        # better than a 500 on a printed invoice.
        return ""


@register.filter(name="jalali_datetime")
def jalali_datetime(value):
    """`۱۴۰۵/۰۵/۲۵ ۱۴:۳۰` in Tehran local time."""
    try:
        return jalali.format_datetime(value)
    except (ValueError, TypeError, AttributeError):
        return ""


@register.simple_tag(takes_context=True)
def panel_date(context, value, kind="date"):
    """A date as this reader's panel shows it (2.40.49): Jalali, with the
    Gregorian day beside it for someone who chose «شمسی و میلادی». Printed
    documents do not use this; they stay Jalali."""
    text = jalali_datetime(value) if kind == "datetime" else jalali_date(value)
    if not text or context.get("panel_calendar_display") != "jalali_gregorian":
        return text
    try:
        gregorian = jalali.format_gregorian(value)
    except (ValueError, TypeError, AttributeError):
        return text
    return f"{text} ({gregorian})" if gregorian else text


@register.filter(name="jalali_long")
def jalali_long(value):
    """`۲۵ مرداد ۱۴۰۵`, for a document heading."""
    try:
        return jalali.format_long_date(value)
    except (ValueError, TypeError, AttributeError):
        return ""
